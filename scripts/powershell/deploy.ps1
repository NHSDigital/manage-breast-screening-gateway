#Requires -Version 5.1
<#
.SYNOPSIS
    Deploy the Manage Breast Screening Gateway using a Blue/Green strategy.
.DESCRIPTION
    Automates environment bootstrapping (Choco, Python, uv), package extraction,
    virtual environment setup, and Windows Service management for the Gateway.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $false)]
    [string]$ZipPath,

    [Parameter()]
    [string]$BaseInstallPath = "C:\Program Files\NHS\ManageBreastScreeningGateway",

    [Parameter()]
    [switch]$Bootstrap,

    [Parameter()]
    [int]$KeepReleases = 3,

    [Parameter()]
    [string]$PythonVersion,

    [Parameter()]
    [int]$ServiceStopTimeoutSeconds = 30,

    [Parameter()]
    [int]$HealthCheckRetries = 5,

    [Parameter()]
    [int]$HealthCheckIntervalSeconds = 2,

    [Parameter()]
    [string]$GitHubRepo = "NHSDigital/manage-breast-screening-gateway",

    [Parameter()]
    [string]$ReleaseTag = "latest",

    [Parameter()]
    [string]$GitHubToken
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# -- Logging ------------------------------------------------------------------

$deploymentLogsDir = Join-Path $BaseInstallPath "logs\deployments"
if (-not (Test-Path $deploymentLogsDir)) {
    New-Item -ItemType Directory -Path $deploymentLogsDir -Force | Out-Null
}
$deploymentLogFile = Join-Path $deploymentLogsDir "deployment-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss.fff"
    $logEntry = "[$timestamp] [$Level] $Message"
    Add-Content -Path $deploymentLogFile -Value $logEntry
    switch ($Level) {
        "ERROR"   { Write-Host $logEntry -ForegroundColor Red }
        "WARNING" { Write-Host $logEntry -ForegroundColor Yellow }
        "SUCCESS" { Write-Host $logEntry -ForegroundColor Green }
        default   { Write-Host $logEntry -ForegroundColor Gray }
    }
}

# -- Helpers ------------------------------------------------------------------

function Invoke-Nssm {
    param([string]$NssmPath, [string[]]$Arguments, [string]$Description)
    & $NssmPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM failed (exit $LASTEXITCODE): $Description -- nssm $($Arguments -join ' ')"
    }
}

function Get-PythonVersionFromPyproject {
    param([string]$PyprojectPath)
    if (-not (Test-Path $PyprojectPath)) { return $null }
    $content = Get-Content $PyprojectPath -Raw
    if ($content -match 'requires-python\s*=\s*">=(\d+\.\d+)') { return $Matches[1] }
    return $null
}

function Get-PythonVersionFromZip {
    param([string]$ArchivePath)
    if (-not $ArchivePath -or -not (Test-Path $ArchivePath)) { return $null }
    Add-Type -Assembly System.IO.Compression.FileSystem
    $zip = $null
    try {
        $zip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
        $entry = $zip.Entries | Where-Object { $_.Name -eq "pyproject.toml" } | Select-Object -First 1

        if ($entry) {
            $reader = New-Object System.IO.StreamReader($entry.Open())
            $content = $reader.ReadToEnd()
            $reader.Close()
            if ($content -match 'requires-python\s*=\s*">=(\d+\.\d+)') { return $Matches[1] }
        }

        # Check for inner ZIP (wrapper package from CI artifacts)
        $innerZipEntry = $zip.Entries | Where-Object { $_.FullName -like "*.zip" } | Select-Object -First 1
        if ($innerZipEntry) {
            $zip.Dispose(); $zip = $null
            $tempInner = Join-Path $env:TEMP "deploy-pyver-$([guid]::NewGuid().ToString().Substring(0,8)).zip"
            try {
                $outerZip = [System.IO.Compression.ZipFile]::OpenRead($ArchivePath)
                $innerEntry = $outerZip.Entries | Where-Object { $_.FullName -eq $innerZipEntry.FullName } | Select-Object -First 1
                [System.IO.Compression.ZipFileExtensions]::ExtractToFile($innerEntry, $tempInner, $true)
                $outerZip.Dispose()

                $innerZip = [System.IO.Compression.ZipFile]::OpenRead($tempInner)
                $innerPyproject = $innerZip.Entries | Where-Object { $_.Name -eq "pyproject.toml" } | Select-Object -First 1
                if ($innerPyproject) {
                    $reader = New-Object System.IO.StreamReader($innerPyproject.Open())
                    $content = $reader.ReadToEnd()
                    $reader.Close()
                    if ($content -match 'requires-python\s*=\s*">=(\d+\.\d+)') {
                        $innerZip.Dispose()
                        return $Matches[1]
                    }
                }
                $innerZip.Dispose()
            } finally {
                if (Test-Path $tempInner) { Remove-Item $tempInner -Force -ErrorAction SilentlyContinue }
            }
        }
    } catch {
        Write-Log "Could not read Python version from archive: $_" "WARNING"
        return $null
    } finally {
        if ($zip) { $zip.Dispose() }
    }
    return $null
}

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

# -- Bootstrap ----------------------------------------------------------------

if ($Bootstrap) {
    Write-Log "Bootstrapping system environment..." "INFO"

    if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
        Write-Log "Installing Chocolatey..." "INFO"
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
        $env:Path += ";$env:ALLUSERSPROFILE\chocolatey\bin"
    }

    $existingPython = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($existingPython) {
        Write-Log "Python already installed: $($existingPython.Source)" "INFO"
    } else {
        $targetPythonVersion = $PythonVersion
        if (-not $targetPythonVersion) {
            $targetPythonVersion = Get-PythonVersionFromPyproject (Join-Path $PSScriptRoot "..\..\pyproject.toml")
        }
        if (-not $targetPythonVersion -and $ZipPath) {
            Write-Log "Reading Python version from package archive..." "INFO"
            $targetPythonVersion = Get-PythonVersionFromZip $ZipPath
        }
        if (-not $targetPythonVersion) {
            throw "Python version could not be determined. Supply -PythonVersion, ensure pyproject.toml is accessible, or provide a ZipPath containing pyproject.toml."
        }
        Write-Log "Installing Python $targetPythonVersion..." "INFO"
        choco install python --version "$targetPythonVersion.0" -y --no-progress
    }

    if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
        Write-Log "Installing uv..." "INFO"
        choco install uv -y --no-progress
    }

    if (-not (Get-Command nssm.exe -ErrorAction SilentlyContinue)) {
        Write-Log "Installing NSSM..." "INFO"
        choco install nssm -y --no-progress
    }
}

# -- Package Acquisition ------------------------------------------------------

$downloadDir = Join-Path $BaseInstallPath "downloads"
if (-not (Test-Path $downloadDir)) {
    New-Item -ItemType Directory -Path $downloadDir -Force | Out-Null
}

if (-not $ZipPath) {
    Write-Log "Downloading from GitHub release..." "INFO"

    if ($ReleaseTag -eq "latest") {
        $apiUrl = "https://api.github.com/repos/$GitHubRepo/releases/latest"
    } else {
        $apiUrl = "https://api.github.com/repos/$GitHubRepo/releases/tags/$ReleaseTag"
    }

    $headers = @{ "Accept" = "application/vnd.github+json"; "User-Agent" = "Gateway-Deploy-Script" }
    if ($GitHubToken) { $headers["Authorization"] = "Bearer $GitHubToken" }

    Write-Log "Querying release: $apiUrl" "INFO"
    try {
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
        $release = Invoke-RestMethod -Uri $apiUrl -Headers $headers -ErrorAction Stop
    } catch {
        throw "Could not retrieve release from $apiUrl. If the repo is private, supply -GitHubToken. Error: $_"
    }

    Write-Log "Release found: $($release.tag_name) - $($release.name)" "INFO"

    $zipAsset = $release.assets | Where-Object { $_.name -like "gateway-*.zip" -and $_.name -notlike "*.sha256" } | Select-Object -First 1
    if (-not $zipAsset) {
        throw "No gateway-*.zip asset in release $($release.tag_name). Available: $(($release.assets | ForEach-Object { $_.name }) -join ', ')"
    }

    $shaAsset = $release.assets | Where-Object { $_.name -eq "$($zipAsset.name).sha256" } | Select-Object -First 1

    $ZipPath = Join-Path $downloadDir $zipAsset.name
    $downloadHeaders = @{ "Accept" = "application/octet-stream"; "User-Agent" = "Gateway-Deploy-Script" }
    if ($GitHubToken) { $downloadHeaders["Authorization"] = "Bearer $GitHubToken" }

    $sizeMB = [math]::Round($zipAsset.size / 1MB, 1)
    Write-Log "Downloading $($zipAsset.name) ($sizeMB MB)..." "INFO"
    Invoke-WebRequest -Uri $zipAsset.browser_download_url -Headers $downloadHeaders -OutFile $ZipPath -UseBasicParsing -ErrorAction Stop
    Write-Log "Downloaded to $ZipPath" "SUCCESS"

    if ($shaAsset) {
        $shaDownloadPath = Join-Path $downloadDir $shaAsset.name
        Invoke-WebRequest -Uri $shaAsset.browser_download_url -Headers $downloadHeaders -OutFile $shaDownloadPath -UseBasicParsing -ErrorAction Stop
        Write-Log "Downloaded checksum" "SUCCESS"
    }
}

# -- Validation ---------------------------------------------------------------

$pythonExe = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonExe) { throw "Python not found in PATH. Run with -Bootstrap or install manually." }

$uvExe = Get-Command uv.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $uvExe) { throw "uv not found in PATH. Run with -Bootstrap or install manually." }

$nssmExe = Get-Command nssm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $nssmExe) { throw "NSSM not found in PATH. Run with -Bootstrap or install manually." }

if (-not (Test-Path $ZipPath)) { throw "Package not found at $ZipPath." }

$shaPath = "$ZipPath.sha256"
if (Test-Path $shaPath) {
    Write-Log "Verifying archive integrity..." "INFO"
    $expectedHash = (Get-Content $shaPath).Split(' ')[0].Trim()
    $actualHash = (Get-FileHash -Path $ZipPath -Algorithm SHA256).Hash.ToLower()
    if ($actualHash -ne $expectedHash.ToLower()) {
        throw "SHA256 mismatch. Expected: $expectedHash, Actual: $actualHash"
    }
    Write-Log "Integrity check passed." "SUCCESS"
}

# -- Prepare Structure --------------------------------------------------------

$releasesDir = Join-Path $BaseInstallPath "releases"
$dataDir = Join-Path $BaseInstallPath "data"
$logsDir = Join-Path $BaseInstallPath "logs"
$currentJunction = Join-Path $BaseInstallPath "current"

foreach ($dir in @($releasesDir, $dataDir, $logsDir)) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
}

$services = @(
    @{ Name = "Gateway-Relay"; Script = "relay_listener.py" },
    @{ Name = "Gateway-PACS"; Script = "pacs_main.py" },
    @{ Name = "Gateway-MWL"; Script = "mwl_main.py" },
    @{ Name = "Gateway-Upload"; Script = "upload_main.py" }
)

# -- Extraction ---------------------------------------------------------------

$version = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) -replace 'gateway-', ''
$versionDir = Join-Path $releasesDir $version

Write-Log "Deploying version: $version" "INFO"

# If redeploying the same version, stop services to release .pyd file locks
if (Test-Path $versionDir) {
    Write-Log "Version directory exists. Stopping services to release file locks..." "WARNING"
    Stop-AllServices -Services $services -TimeoutSeconds $ServiceStopTimeoutSeconds
}

$stagingDir = Join-Path $env:TEMP "gateway-deploy-staging-$([guid]::NewGuid().ToString().Substring(0,8))"
New-Item -ItemType Directory -Path $stagingDir -Force | Out-Null

Add-Type -Assembly System.IO.Compression.FileSystem

try {
    Write-Log "Extracting package..." "INFO"
    [System.IO.Compression.ZipFile]::ExtractToDirectory($ZipPath, $stagingDir)

    $innerZip = Get-ChildItem -Path $stagingDir -Filter "*.zip" | Select-Object -First 1

    if ($innerZip) {
        Write-Log "Detected inner package: $($innerZip.Name)" "INFO"

        # Verify inner archive integrity if checksum present
        $innerSha = Get-ChildItem -Path $stagingDir -Filter "$($innerZip.Name).sha256" | Select-Object -First 1
        if ($innerSha) {
            $expectedHash = (Get-Content $innerSha.FullName).Split(' ')[0].Trim()
            $actualHash = (Get-FileHash -Path $innerZip.FullName -Algorithm SHA256).Hash.ToLower()
            if ($actualHash -ne $expectedHash.ToLower()) {
                throw "Inner archive SHA256 mismatch. Expected: $expectedHash, Actual: $actualHash"
            }
            Write-Log "Inner integrity check passed." "SUCCESS"
        }

        if (Test-Path $versionDir) { Remove-Item -Path $versionDir -Recurse -Force -Confirm:$false }
        [System.IO.Compression.ZipFile]::ExtractToDirectory($innerZip.FullName, $versionDir)
    } else {
        if (Test-Path $versionDir) { Remove-Item -Path $versionDir -Recurse -Force -Confirm:$false }
        Move-Item -Path $stagingDir -Destination $versionDir
    }
} finally {
    if (Test-Path $stagingDir) { Remove-Item -Path $stagingDir -Recurse -Force -Confirm:$false }
}

# Flatten nested folder structure (single top-level directory inside archive)
$extractedItems = Get-ChildItem -Path $versionDir
if ($extractedItems.Count -eq 1 -and $extractedItems[0].PSIsContainer) {
    Write-Log "Flattening nested folder structure..." "INFO"
    $nestedPath = $extractedItems[0].FullName
    Get-ChildItem -Path $nestedPath | Move-Item -Destination $versionDir
    Remove-Item -Path $nestedPath -Force
}

if (-not (Test-Path (Join-Path $versionDir "pyproject.toml"))) {
    throw "pyproject.toml not found in extracted package at $versionDir."
}
if (-not (Test-Path (Join-Path $versionDir "uv.lock"))) {
    throw "uv.lock not found in extracted package at $versionDir."
}

# -- Environment Setup --------------------------------------------------------

Write-Log "Setting up virtual environment..." "INFO"
Push-Location $versionDir
try {
    & $uvExe venv --python $pythonExe
    if ($LASTEXITCODE -ne 0) { throw "uv venv failed (exit $LASTEXITCODE)" }

    & $uvExe sync --frozen
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed (exit $LASTEXITCODE)" }

    # Pre-compile bytecache to avoid slow first-run compilation under NSSM
    Write-Log "Pre-compiling bytecache..." "INFO"
    $venvPythonExe = Join-Path $versionDir ".venv\Scripts\python.exe"
    $srcDir = Join-Path $versionDir "src"
    & $venvPythonExe -m compileall -q $srcDir
    & $venvPythonExe -c "import compileall; compileall.compile_path(quiet=1)"
} catch {
    Write-Log "Environment setup failed: $_" "ERROR"
    throw
} finally {
    Pop-Location
}

# -- Service Helpers ----------------------------------------------------------

foreach ($svc in $services) {
    $batPath = Join-Path $versionDir "start-$($svc.Name).bat"
    $scriptPath = Join-Path "src" $svc.Script
    $batContent = @(
        '@echo off',
        'cd /d "%~dp0"',
        'set "PYTHONPATH=src"',
        ('".venv\Scripts\python.exe" "' + $scriptPath + '"')
    ) -join "`r`n"
    [System.IO.File]::WriteAllText($batPath, $batContent, [System.Text.Encoding]::ASCII)
}

# -- Cutover ------------------------------------------------------------------

Write-Log "Starting cutover..." "INFO"
$cutoverStart = Get-Date

# Capture previous junction target for rollback
$previousVersionDir = $null
if (Test-Path $currentJunction) {
    $junctionItem = Get-Item $currentJunction
    if ($junctionItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        $previousVersionDir = $junctionItem.Target
        if ($previousVersionDir -is [array]) { $previousVersionDir = $previousVersionDir[0] }
        Write-Log "Previous version: $previousVersionDir" "INFO"
    }
}

# Stop services (skips already-stopped services from redeploy path)
Stop-AllServices -Services $services -TimeoutSeconds $ServiceStopTimeoutSeconds

# -- Cleanup (while services are stopped -- no .pyd locks) --------------------

# Remove .trash directories from previous deployments
Get-ChildItem -Path $releasesDir -Directory -Filter ".trash-*" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item -Path $_.FullName -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
}

$cleanupProtected = @($versionDir)
if ($previousVersionDir) { $cleanupProtected += $previousVersionDir }

$oldReleases = Get-ChildItem -Path $releasesDir -Directory |
    Where-Object { $_.Name -notlike ".trash-*" } |
    Sort-Object CreationTime -Descending |
    Select-Object -Skip $KeepReleases
foreach ($rel in $oldReleases) {
    if ($rel.FullName -in $cleanupProtected) { continue }
    Write-Log "Removing old release: $($rel.Name)" "INFO"
    try {
        Remove-Item -Path $rel.FullName -Recurse -Force -Confirm:$false
    } catch {
        $trashName = ".trash-$($rel.Name)-$([guid]::NewGuid().ToString().Substring(0,8))"
        $trashPath = Join-Path $releasesDir $trashName
        try {
            [System.IO.Directory]::Move($rel.FullName, $trashPath)
            Write-Log "Deferred cleanup of $($rel.Name) to next deployment." "WARNING"
        } catch {
            Write-Log "Could not remove $($rel.Name): $_" "WARNING"
        }
    }
}

# Switch junction
if (Test-Path $currentJunction) { (Get-Item $currentJunction).Delete() }
New-Item -ItemType Junction -Path $currentJunction -Target $versionDir -Force | Out-Null

# Register and start services
$startedServices = @()
$cutoverFailed = $false

foreach ($svc in $services) {
    $batPath = Join-Path $currentJunction "start-$($svc.Name).bat"

    # Remove+reinstall to clear NSSM throttle state from previous failures
    $existingSvc = Get-Service -Name $svc.Name -ErrorAction SilentlyContinue
    if ($existingSvc) {
        & $nssmExe remove $svc.Name confirm 2>&1 | Out-Null
        $retries = 10
        while ((Get-Service -Name $svc.Name -ErrorAction SilentlyContinue) -and $retries -gt 0) {
            Start-Sleep -Milliseconds 500
            $retries--
        }
    }

    Invoke-Nssm -NssmPath $nssmExe -Arguments @("install", $svc.Name, "$batPath") -Description "install $($svc.Name)"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "AppDirectory", "$currentJunction") -Description "set AppDirectory"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "Description", "Manage Breast Screening Gateway - $($svc.Name)") -Description "set Description"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "Start", "SERVICE_AUTO_START") -Description "set Start"

    $svcLog = Join-Path $logsDir "$($svc.Name).log"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "AppStdout", "$svcLog") -Description "set AppStdout"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "AppStderr", "$svcLog") -Description "set AppStderr"

    try {
        Start-Service -Name $svc.Name
        $startedServices += $svc.Name
    } catch {
        Write-Log "Failed to start $($svc.Name): $_" "ERROR"
        $cutoverFailed = $true
        break
    }
}

# -- Health Check -------------------------------------------------------------

if (-not $cutoverFailed) {
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
            Write-Log "$svcName check $i/$($HealthCheckRetries) - status: $($svcStatus.Status)" "WARNING"
        }
        if (-not $healthy) {
            Write-Log "$svcName failed health check." "ERROR"
            $cutoverFailed = $true
            break
        }
    }
}

# -- Rollback on Failure ------------------------------------------------------

if ($cutoverFailed) {
    Write-Log "Deployment failed. Rolling back..." "ERROR"

    foreach ($svcName in $startedServices) {
        Stop-Service -Name $svcName -Force -ErrorAction SilentlyContinue
    }

    if ($previousVersionDir -and (Test-Path $previousVersionDir)) {
        if (Test-Path $currentJunction) { (Get-Item $currentJunction).Delete() }
        New-Item -ItemType Junction -Path $currentJunction -Target $previousVersionDir -Force | Out-Null

        foreach ($svc in $services) {
            $batPath = Join-Path $currentJunction "start-$($svc.Name).bat"
            if (Test-Path $batPath) {
                & $nssmExe set $svc.Name Application "$batPath" 2>&1 | Out-Null
                & $nssmExe set $svc.Name AppDirectory "$currentJunction" 2>&1 | Out-Null
            }
        }

        foreach ($svc in $services) {
            Start-Service -Name $svc.Name -ErrorAction SilentlyContinue
        }
        Write-Log "Rolled back to previous version." "WARNING"
    } else {
        Write-Log "No previous version for rollback. Services are stopped." "ERROR"
    }

    throw "Deployment of version $version failed. Rollback was attempted."
}

$cutoverDuration = ((Get-Date) - $cutoverStart).TotalSeconds
Write-Log "Deployment of version $version completed in $([math]::Round($cutoverDuration, 2))s." "SUCCESS"
