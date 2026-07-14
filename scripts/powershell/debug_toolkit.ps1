# Live-clinic debugging toolkit for the gateway VM.
#
# Usage: RDP to the gateway VM, open PowerShell, then dot-source this file:
#
#   . .\debug_toolkit.ps1
#
# All Gw* query functions are READ-ONLY (SQLite opened with mode=ro).
# The only mutating helper is Restart-GwService, which prompts first.

$script:GwBase    = "C:\Program Files\NHS\ManageBreastScreeningGateway"
$script:GwPython  = Join-Path $GwBase "current\.venv\Scripts\python.exe"
$script:GwLogs    = Join-Path $GwBase "logs"
$script:GwStorage = Join-Path $GwBase "data\storage"
$script:GwMwlDb   = Join-Path $GwBase "data\worklist.db"
$script:GwPacsDb  = Join-Path $GwBase "data\pacs.db"
$script:GwServices = @("Gateway-Relay", "Gateway-MWL", "Gateway-PACS", "Gateway-Upload")

# ── SQLite (via the app's venv Python — no sqlite3.exe needed) ────────────────

function Invoke-GwSql {
    <# Run an arbitrary read-only SQL query. Usage:
       Invoke-GwSql -Db mwl  -Query "SELECT * FROM worklist_items LIMIT 5"
       Invoke-GwSql -Db pacs -Query "SELECT count(*) AS n FROM stored_instances" #>
    param(
        [Parameter(Mandatory)][ValidateSet("mwl", "pacs")][string]$Db,
        [Parameter(Mandatory)][string]$Query
    )
    $dbPath = if ($Db -eq "mwl") { $GwMwlDb } else { $GwPacsDb }
    $dbUri = "file:///" + ($dbPath -replace '\\', '/') + "?mode=ro"
    $py = @"
import sqlite3, json, sys
conn = sqlite3.connect(r'$dbUri', uri=True, timeout=10)
conn.row_factory = sqlite3.Row
try:
    rows = [dict(r) for r in conn.execute(sys.argv[1])]
    print(json.dumps(rows, indent=2, default=str))
finally:
    conn.close()
"@
    & $GwPython -c $py $Query | ConvertFrom-Json
}

function Get-GwWorklist {
    <# Today's worklist items (or all with -All). The MWL serves these to the modality. #>
    param([switch]$All)
    $where = if ($All) { "1=1" } else { "scheduled_date = strftime('%Y%m%d','now')" }
    Invoke-GwSql -Db mwl -Query @"
SELECT accession_number, patient_name, patient_id, scheduled_date, scheduled_time,
       status, study_instance_uid, updated_at
FROM worklist_items WHERE $where
ORDER BY scheduled_time
"@ | Format-Table accession_number, patient_name, scheduled_time, status, updated_at -AutoSize
}

function Get-GwWorklistItem {
    <# Full detail for one worklist item. Usage: Get-GwWorklistItem ACC20260707XXXX #>
    param([Parameter(Mandatory)][string]$AccessionNumber)
    Invoke-GwSql -Db mwl -Query "SELECT * FROM worklist_items WHERE accession_number = '$AccessionNumber'"
}

function Get-GwImages {
    <# Images received today, grouped per accession, with upload progress. #>
    Invoke-GwSql -Db pacs -Query @"
SELECT accession_number,
       count(*)                                                    AS images,
       sum(CASE WHEN upload_status = 'COMPLETE' THEN 1 ELSE 0 END) AS uploaded,
       sum(CASE WHEN upload_status = 'FAILED'   THEN 1 ELSE 0 END) AS failed,
       printf('%.1f MB', sum(file_size) / 1048576.0)               AS size,
       max(created_at)                                             AS last_received
FROM stored_instances
WHERE date(created_at) = date('now')
GROUP BY accession_number
ORDER BY last_received DESC
"@ | Format-Table -AutoSize
}

function Get-GwImageDetail {
    <# Per-image rows for one accession: file path, upload status, errors. #>
    param([Parameter(Mandatory)][string]$AccessionNumber)
    Invoke-GwSql -Db pacs -Query @"
SELECT sop_instance_uid, storage_path, file_size, source_aet, created_at,
       upload_status, upload_attempt_count, last_upload_attempt, upload_error
FROM stored_instances WHERE accession_number = '$AccessionNumber'
ORDER BY created_at
"@
}

function Get-GwUploadFailures {
    <# All instances not yet uploaded to Manage (PENDING/UPLOADING/FAILED), with errors. #>
    Invoke-GwSql -Db pacs -Query @"
SELECT accession_number, sop_instance_uid, upload_status, upload_attempt_count,
       last_upload_attempt, substr(upload_error, 1, 200) AS upload_error
FROM stored_instances
WHERE upload_status != 'COMPLETE'
ORDER BY created_at
"@ | Format-Table -AutoSize
}

# ── File system ───────────────────────────────────────────────────────────────

function Get-GwDicomFiles {
    <# DICOM files written to storage in the last N hours (default 8). #>
    param([int]$Hours = 8)
    Get-ChildItem -Path $GwStorage -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -gt (Get-Date).AddHours(-$Hours) } |
        Sort-Object LastWriteTime |
        Format-Table LastWriteTime, @{n = "MB"; e = { "{0:N1}" -f ($_.Length / 1MB) } }, FullName -AutoSize
}

function Get-GwDiskSpace {
    Get-PSDrive C | Format-Table Name,
        @{n = "UsedGB"; e = { "{0:N1}" -f ($_.Used / 1GB) } },
        @{n = "FreeGB"; e = { "{0:N1}" -f ($_.Free / 1GB) } } -AutoSize
}

# ── Logs ──────────────────────────────────────────────────────────────────────

function Watch-GwLog {
    <# Live-tail one service log. Usage: Watch-GwLog PACS   (Relay|MWL|PACS|Upload) #>
    param([Parameter(Mandatory)][ValidateSet("Relay", "MWL", "PACS", "Upload")][string]$Service)
    Get-Content -Path (Join-Path $GwLogs "Gateway-$Service.log") -Tail 50 -Wait
}

function Search-GwLogs {
    <# Search all four service logs. Usage: Search-GwLogs "ERROR|Traceback" -Last 200 #>
    param([string]$Pattern = "ERROR|Traceback|Exception", [int]$Last = 100)
    Get-ChildItem -Path (Join-Path $GwLogs "Gateway-*.log") | ForEach-Object {
        Select-String -Path $_.FullName -Pattern $Pattern | Select-Object -Last $Last
    }
}

function Get-GwDeployLog {
    <# Most recent deployment log (what version went out, and when). #>
    Get-ChildItem -Path (Join-Path $GwLogs "deployments") -Filter "deploy-*" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content
}

# ── Service and network health ───────────────────────────────────────────────

function Get-GwHealth {
    <# One-screen health check: services, ports, relay connection, disk, version. #>
    Write-Host "`n── Services ──" -ForegroundColor Cyan
    Get-Service -Name "Gateway-*" | Format-Table Name, Status, StartType -AutoSize

    Write-Host "── Listening ports (MWL 104, PACS 11112) ──" -ForegroundColor Cyan
    Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
        Where-Object { $_.LocalPort -in 104, 11112 } |
        Format-Table LocalAddress, LocalPort, OwningProcess -AutoSize

    Write-Host "── Relay listener (last connection lines) ──" -ForegroundColor Cyan
    Select-String -Path (Join-Path $GwLogs "Gateway-Relay.log") -Pattern "Connecting to Azure Relay|Connected - waiting|credentials verified|ERROR" |
        Select-Object -Last 5 | ForEach-Object { $_.Line }

    Write-Host "`n── Current version ──" -ForegroundColor Cyan
    (Get-Item (Join-Path $GwBase "current")).Target

    Write-Host "`n── Disk ──" -ForegroundColor Cyan
    Get-GwDiskSpace
}

function Restart-GwService {
    <# Restart one gateway service (prompts for confirmation).
       Usage: Restart-GwService Gateway-Relay #>
    param([Parameter(Mandatory)][ValidateSet("Gateway-Relay", "Gateway-MWL", "Gateway-PACS", "Gateway-Upload")][string]$Name)
    Restart-Service -Name $Name -Confirm
    Get-Service -Name $Name
}

Write-Host "Gateway debug toolkit loaded. Key commands:" -ForegroundColor Green
Write-Host "  Get-GwHealth            - services / ports / relay / disk, one screen"
Write-Host "  Get-GwWorklist          - today's MWL items"
Write-Host "  Get-GwWorklistItem ACC  - one item in full"
Write-Host "  Get-GwImages            - today's received images + upload progress"
Write-Host "  Get-GwImageDetail ACC   - per-image detail for one accession"
Write-Host "  Get-GwUploadFailures    - anything not uploaded to Manage"
Write-Host "  Get-GwDicomFiles        - files on disk, last 8h"
Write-Host "  Watch-GwLog PACS        - live tail (Relay|MWL|PACS|Upload)"
Write-Host "  Search-GwLogs           - grep ERROR/Traceback across all logs"
Write-Host "  Invoke-GwSql            - arbitrary read-only SQL (mwl|pacs)"
