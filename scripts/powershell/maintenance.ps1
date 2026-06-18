param(
    [string]$BaseInstallPath = "C:\Program Files\NHS\ManageBreastScreeningGateway",
    [Parameter(Mandatory)]
    [string]$Action
)

# -- Set common vars -------------------------------------------------------

$logsDir = Join-Path $BaseInstallPath "logs"
$maintenanceLogFile = Join-Path $logsDir "maintenance.log"

$services = Get-Service |
    Where-Object { $_.Name -like "Gateway-*" } |
    ForEach-Object {
        @{ Name = $_.Name }
    }

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $logEntry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $maintenanceLogFile -Value $logEntry
    switch ($Level) {
        "ERROR"   { Write-Host $logEntry -ForegroundColor Red }
        "WARNING" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        default   { Write-Host $logEntry -ForegroundColor Gray }
    }
}

# -- Service control helpers -------------------------------------------------------

function Stop-AllServices {
    param([array]$Services, [int]$TimeoutSeconds)
    foreach ($svc in $Services) {
        $status = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
        if (-not $status -or $status.Status -eq 'Stopped') { continue }

        Write-Log "Stopping $($svc.Name) (timeout: ${TimeoutSeconds}s)..." "INFO"
        Stop-Service -Name $svc.Name -Force

        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
            $current = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
            if (-not $current -or $current.Status -eq 'Stopped') { break }
            Start-Sleep -Milliseconds 500
        }
        $stopwatch.Stop()

        $finalStatus = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
        if ($finalStatus -and $finalStatus.Status -ne 'Stopped') {
            throw "Service $($svc.Name) did not stop within ${TimeoutSeconds}s (state: $($finalStatus.Status))."
        }
        Write-Log "$($svc.Name) stopped in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 1))s." "INFO"
    }
}

function Start-AllServices {
    param(
        [array]$Services, [int]$TimeoutSeconds
    )

    foreach ($svc in $Services) {
        Write-Log "Starting $($svc.Name)..." "INFO"

        Start-Service -Name $svc.Name

        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        while ($stopwatch.Elapsed.TotalSeconds -lt $TimeoutSeconds) {
            $status = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
            if ($status -and $status.Status -eq 'Running') { break }
            Start-Sleep -Milliseconds 500
        }
        $stopwatch.Stop()

        $finalStatus = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
        if (-not $finalStatus -or $finalStatus.Status -ne 'Running') {
            throw "Service $($svc.Name) did not start within ${TimeoutSeconds}s (state: $($finalStatus.Status))."
        }

        Write-Log "$($svc.Name) started in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 1))s." "SUCCESS"
    }
}

# -- Database backup ----------------------------------------------------------

function Invoke-DatabaseBackup {
    param(
        [string]$BaseInstallPath,
        [string]$DbServiceName
    )

    Write-Log "Starting database backup..." "INFO"

    Set-Item -Path env:PYTHONPATH -Value "$BaseInstallPath\current\scripts\python"
    Set-Item -Path env:BACKUP_PATH -Value "$BaseInstallPath\data\backups"
    Set-Item -Path env:MAX_BACKUPS -Value 5

    if ($DbServiceName -eq "MWL") {
        Set-Item -Path env:DB_PATH -Value "$BaseInstallPath\data\worklist.db"
        Set-Item -Path env:TABLE_NAME -Value "worklist_items"
    }
    if ($DbServiceName -eq "PACS") {
        Set-Item -Path env:DB_PATH -Value "$BaseInstallPath\data\pacs.db"
        Set-Item -Path env:TABLE_NAME -Value "stored_instances"
    }
    $pythonExe = Join-Path $BaseInstallPath "current\.venv\Scripts\python.exe"
    $databaseScript = Join-Path $BaseInstallPath "current\scripts\python\database.py"
    & $pythonExe $databaseScript

    if ($LASTEXITCODE -ne 0) {
        Write-Log "Database backup failed with exit code $LASTEXITCODE" "ERROR"
        throw "Database backup failed with exit code $LASTEXITCODE"
    }

    Write-Log "Database backup completed successfully." "SUCCESS"
}

# -- Log Rotation -------------------------------------------------------------

function Rotate-LogFile {
    param(
        [Parameter(Mandatory)]
        [string]$LogFile,

        [int]$RetainCount = 5
    )

    if (-not (Test-Path $LogFile)) {
        return
    }

    # Remove oldest
    $oldest = "$LogFile.$RetainCount"
    if (Test-Path $oldest) {
        Remove-Item $oldest -Force
    }

    # Shift existing rotations
    for ($i = $RetainCount - 1; $i -ge 1; $i--) {
        $src = "$LogFile.$i"
        $dst = "$LogFile." + ($i + 1)

        if (Test-Path $src) {
            Move-Item $src $dst -Force
        }
    }

    Move-Item $LogFile "$LogFile.1" -Force
}

function Rotate-ServiceLogs {
    param(
        [array]$Services,
        [string]$LogsDir
    )

    foreach ($svc in $Services) {
        $logFile = Join-Path $LogsDir "$($svc.Name).log"
        Rotate-LogFile -LogFile $logFile -RetainCount 5
    }
}

# -- PACS archiving -------------------------------------------------------------

function Archive-PACS {
    param(
        [string]$BaseInstallPath
    )

    Write-Log "Archiving PACS files..." "INFO"

    $pacsDir = Join-Path $BaseInstallPath "data\storage\*"
    $archiveZip = Join-Path $BaseInstallPath "data\storage.zip"

    Compress-Archive -Path $pacsDir -DestinationPath $archiveZip -Force

    Write-Log "PACS files archived to $archiveZip." "INFO"

    Remove-Item $pacsDir -Recurse -Force

    Write-Log "PACS files removed from storage directory." "INFO"

    Write-Log "PACS files archived successfully." "SUCCESS"
}

# -- Main ----------------------------------------------------------------------

$startStopTimeoutSeconds = 30

switch ($Action) {

    "RotateLogs" {
        Stop-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
        Rotate-ServiceLogs -Services $services -LogsDir $logsDir
        Start-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
    }

    "BackupPACSDatabase" {
        Stop-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
        Invoke-DatabaseBackup -BaseInstallPath $BaseInstallPath -DbServiceName "PACS"
        Archive-PACS -BaseInstallPath $BaseInstallPath
        Start-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
    }

    "BackupMWLDatabase" {
        Stop-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
        Invoke-DatabaseBackup -BaseInstallPath $BaseInstallPath -DbServiceName "MWL"
        Start-AllServices -Services $Services -TimeoutSeconds $startStopTimeoutSeconds
    }

    default {
        Write-Log "Unknown action: $Action" "ERROR"
        throw "Unknown action: $Action"
    }
}

exit 0
