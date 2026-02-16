#Requires -Version 5.1
<#
.SYNOPSIS
    Roll back the Manage Breast Screening Gateway to a previous version.
.DESCRIPTION
    Switches the directory junction to a previous release. By default, rolls
    back to the most recent release that is not the currently active one.
    Use -Version to target a specific release directory.
    Designed for urgent fixes; the standard process is fix-forward via deploy.ps1.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseInstallPath = "C:\Program Files\NHS\ManageBreastScreeningGateway",

    [Parameter()]
    [string]$Version,

    [Parameter()]
    [int]$ServiceStopTimeoutSeconds = 30,

    [Parameter()]
    [int]$HealthCheckRetries = 5,

    [Parameter()]
    [int]$HealthCheckIntervalSeconds = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Logging ------------------------------------------------------------------

$deploymentLogsDir = Join-Path $BaseInstallPath "logs\deployments"
if (-not (Test-Path $deploymentLogsDir)) {
    New-Item -ItemType Directory -Path $deploymentLogsDir -Force | Out-Null
}
$logFile = Join-Path $deploymentLogsDir "rollback-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $entry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $entry
    switch ($Level) {
        "ERROR"   { Write-Host $entry -ForegroundColor Red }
        "WARNING" { Write-Host $entry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $entry -ForegroundColor Green }
        default   { Write-Host $entry -ForegroundColor Gray }
    }
}

# -- Paths --------------------------------------------------------------------

$releasesDir = Join-Path $BaseInstallPath "releases"
$currentJunction = Join-Path $BaseInstallPath "current"
$logsDir = Join-Path $BaseInstallPath "logs"

$services = @(
    @{ Name = "Gateway-Relay"; Script = "relay_listener.py" },
    @{ Name = "Gateway-PACS"; Script = "pacs_main.py" },
    @{ Name = "Gateway-MWL"; Script = "mwl_main.py" },
    @{ Name = "Gateway-Upload"; Script = "upload_main.py" }
)

# -- Resolve current version --------------------------------------------------

Write-Log "Starting rollback" "INFO"
Write-Log "Base install path: $BaseInstallPath" "INFO"

if (-not (Test-Path $currentJunction)) {
    throw "No current junction found at $currentJunction. Nothing to roll back."
}

$junctionItem = Get-Item $currentJunction
if (-not ($junctionItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
    throw "$currentJunction exists but is not a junction. Cannot determine current version."
}

$currentTarget = $junctionItem.Target
if ($currentTarget -is [array]) { $currentTarget = $currentTarget[0] }
$currentVersionName = Split-Path $currentTarget -Leaf

Write-Log "Current version: $currentVersionName (target: $currentTarget)" "INFO"

# -- Resolve rollback target --------------------------------------------------

if (-not (Test-Path $releasesDir)) {
    throw "Releases directory not found at $releasesDir."
}

if ($Version) {
    # Explicit version requested
    $targetDir = Join-Path $releasesDir $Version
    if (-not (Test-Path $targetDir)) {
        $available = (Get-ChildItem -Path $releasesDir -Directory | ForEach-Object { $_.Name }) -join ", "
        throw "Version '$Version' not found in $releasesDir. Available: $available"
    }
} else {
    # Default: most recent release that is not the current one
    $candidates = Get-ChildItem -Path $releasesDir -Directory |
        Where-Object { $_.FullName -ne $currentTarget } |
        Sort-Object CreationTime -Descending
    if ($candidates.Count -eq 0) {
        throw "No previous version available for rollback. Only the current version exists."
    }
    $targetDir = $candidates[0].FullName
}

$targetVersionName = Split-Path $targetDir -Leaf

if ($targetDir -eq $currentTarget) {
    Write-Log "Target version ($targetVersionName) is already the active version. Nothing to do." "WARNING"
    return
}

Write-Log "Rollback target: $targetVersionName ($targetDir)" "INFO"

# Verify the target has the expected structure
if (-not (Test-Path (Join-Path $targetDir "pyproject.toml"))) {
    throw "Target version directory is missing pyproject.toml. The release may be corrupted."
}

$hasBatFiles = $true
foreach ($svc in $services) {
    if (-not (Test-Path (Join-Path $targetDir "start-$($svc.Name).bat"))) {
        $hasBatFiles = $false
        break
    }
}
if (-not $hasBatFiles) {
    throw "Target version directory is missing service .bat helpers. The release may be incomplete."
}

# -- List available versions for operator awareness ---------------------------

Write-Log "Available versions:" "INFO"
Get-ChildItem -Path $releasesDir -Directory | Sort-Object CreationTime -Descending | ForEach-Object {
    $marker = ""
    if ($_.FullName -eq $currentTarget) { $marker = " (current)" }
    if ($_.FullName -eq $targetDir) { $marker = " <-- rollback target" }
    Write-Log "  $($_.Name)$marker" "INFO"
}

# -- NSSM check ---------------------------------------------------------------

$nssmExe = Get-Command nssm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $nssmExe) {
    throw "NSSM not found in PATH. Cannot manage services."
}

# -- Stop services ------------------------------------------------------------

Write-Log "Stopping services..." "INFO"
$rollbackStart = Get-Date

foreach ($svc in $services) {
    $status = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
    if ($status -and $status.Status -ne 'Stopped') {
        Write-Log "Stopping $($svc.Name) (timeout: ${ServiceStopTimeoutSeconds}s)..." "INFO"
        Stop-Service -Name $svc.Name -Force

        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($stopwatch.Elapsed.TotalSeconds -lt $ServiceStopTimeoutSeconds) {
            $current = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
            if (-not $current -or $current.Status -eq 'Stopped') { break }
            Start-Sleep -Milliseconds 500
        }
        $stopwatch.Stop()

        $finalStatus = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
        if ($finalStatus -and $finalStatus.Status -ne 'Stopped') {
            throw "Service $($svc.Name) did not stop within ${ServiceStopTimeoutSeconds}s. Aborting rollback."
        }
        Write-Log "$($svc.Name) stopped." "INFO"
    } else {
        Write-Log "$($svc.Name) already stopped or not registered." "INFO"
    }
}

# -- Switch junction ----------------------------------------------------------

Write-Log "Switching junction to $targetVersionName..." "INFO"

(Get-Item $currentJunction).Delete()
New-Item -ItemType Junction -Path $currentJunction -Target $targetDir -Force | Out-Null

Write-Log "Junction updated." "SUCCESS"

# -- Re-register and start services ------------------------------------------

Write-Log "Re-registering and starting services..." "INFO"
$startedServices = @()
$rollbackFailed = $false

foreach ($svc in $services) {
    $batPath = Join-Path $currentJunction "start-$($svc.Name).bat"

    # Remove and reinstall to clear NSSM throttle state
    $existingSvc = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
    if ($existingSvc) {
        & $nssmExe remove $svc.Name confirm 2>&1 | Out-Null
        $retries = 10
        while ((Get-Service -Name $svc.Name -ErrorAction SilentlyContinue) -and $retries -gt 0) {
            Start-Sleep -Milliseconds 500
            $retries--
        }
    }

    & $nssmExe install $svc.Name "$batPath"
    if ($LASTEXITCODE -ne 0) {
        Write-Log "NSSM install failed for $($svc.Name) (exit code $LASTEXITCODE)" "ERROR"
        $rollbackFailed = $true
        break
    }

    & $nssmExe set $svc.Name AppDirectory "$currentJunction" 2>&1 | Out-Null
    & $nssmExe set $svc.Name Description "Manage Breast Screening Gateway - $($svc.Name)" 2>&1 | Out-Null
    & $nssmExe set $svc.Name Start SERVICE_AUTO_START 2>&1 | Out-Null

    $svcLog = Join-Path $logsDir "$($svc.Name).log"
    & $nssmExe set $svc.Name AppStdout "$svcLog" 2>&1 | Out-Null
    & $nssmExe set $svc.Name AppStderr "$svcLog" 2>&1 | Out-Null

    try {
        Start-Service -Name $svc.Name
        $startedServices += $svc.Name
        Write-Log "$($svc.Name) started." "SUCCESS"
    } catch {
        Write-Log "Failed to start $($svc.Name): $_" "ERROR"
        $rollbackFailed = $true
        break
    }
}

# -- Health check -------------------------------------------------------------

if (-not $rollbackFailed) {
    Write-Log "Running health checks..." "INFO"
    foreach ($svcName in $startedServices) {
        $healthy = $false
        for ($i = 1; $i -le $HealthCheckRetries; $i++) {
            Start-Sleep -Seconds $HealthCheckIntervalSeconds
            $svcStatus = Get-Service -Name $svcName -ErrorAction SilentlyContinue
            if ($svcStatus -and $svcStatus.Status -eq 'Running') {
                $healthy = $true
                Write-Log "$svcName healthy (check $i/$HealthCheckRetries)." "SUCCESS"
                break
            }
            Write-Log "$svcName not yet running (check $i/$HealthCheckRetries, status: $($svcStatus.Status))..." "WARNING"
        }
        if (-not $healthy) {
            Write-Log "$svcName failed health check." "ERROR"
            $rollbackFailed = $true
            break
        }
    }
}

# -- Result -------------------------------------------------------------------

$rollbackDuration = ((Get-Date) - $rollbackStart).TotalSeconds

if ($rollbackFailed) {
    Write-Log "Rollback to $targetVersionName completed with errors. Manual intervention required." "ERROR"
    throw "Rollback encountered failures. Check logs: $logFile"
}

Write-Log "Rollback complete: $currentVersionName --> $targetVersionName" "SUCCESS"
Write-Log "Duration: $([math]::Round($rollbackDuration, 2)) seconds" "SUCCESS"
Write-Log "Log: $logFile" "INFO"
