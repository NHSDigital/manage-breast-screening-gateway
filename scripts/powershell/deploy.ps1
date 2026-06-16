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
    [bool]$Bootstrap = $true,

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
    [string]$GitHubToken,

    [Parameter()]
    [string]$EnvContentB64 = "",

    [Parameter()]
    [string]$Environment = "prod"
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

# -- Write .env (when deployed via Arc Run Command) ---------------------------

if ($EnvContentB64) {
    Write-Log "Writing .env from deployment parameter..." "INFO"
    $envBytes = [System.Convert]::FromBase64String($EnvContentB64)
    $envContent = [System.Text.Encoding]::UTF8.GetString($envBytes)
    [System.IO.File]::WriteAllText((Join-Path $BaseInstallPath ".env"), $envContent, (New-Object System.Text.UTF8Encoding $false))
    Write-Log "Written .env to $BaseInstallPath" "SUCCESS"
}

# -- Version Check (skip reinstall if already on this version) ----------------
#
# deploy.ps1 writes a VERSION file after every successful deployment.
# On subsequent runs with the same tag, we exit early to avoid redundant
# reinstalls (e.g. on every main-branch merge when no new release exists).
# New VMs have no VERSION file and always proceed with installation.
# When ReleaseTag is "latest", skip the check — the resolved version is unknown
# at this point and the check would never match.

$versionFile = Join-Path $BaseInstallPath "VERSION"
if ($ReleaseTag -ne "latest" -and (Test-Path $versionFile)) {
    $currentVersion = (Get-Content $versionFile -Raw).Trim()
    if ($currentVersion -eq $ReleaseTag) {
        Write-Log "Already running $ReleaseTag - skipping deployment" "INFO"
        exit 0
    }
    Write-Log "Upgrading from $currentVersion to $ReleaseTag" "INFO"
}

# -- Helpers ------------------------------------------------------------------

function Invoke-Nssm {
    param([string]$NssmPath, [string[]]$Arguments, [string]$Description)
    & $NssmPath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "NSSM failed (exit $LASTEXITCODE): $Description -- nssm $($Arguments -join ' ')"
    }
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

    function Install-WithRetry {
        param([string]$Name, [scriptblock]$Script, [int]$MaxAttempts = 3)
        $attempt = 0
        while ($attempt -lt $MaxAttempts) {
            $attempt++
            try {
                Write-Log "Installing $Name (attempt $attempt/$MaxAttempts)..." "INFO"
                & $Script
                return
            } catch {
                Write-Log "Failed to install ${Name}: $_" "WARNING"
                if ($attempt -lt $MaxAttempts) {
                    $wait = 10 * $attempt
                    Write-Log "Waiting ${wait}s before retry..." "INFO"
                    Start-Sleep -Seconds $wait
                }
            }
        }
        throw "Failed to install $Name after $MaxAttempts attempts."
    }

    if (-not (Get-Command choco.exe -ErrorAction SilentlyContinue)) {
        Install-WithRetry "Chocolatey" {
            Set-ExecutionPolicy Bypass -Scope Process -Force
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
            $scriptUrl = 'https://community.chocolatey.org/install.ps1'
            Invoke-Expression (Invoke-WebRequest -UseBasicParsing -Uri $scriptUrl).Content
        }
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
    }

    $existingPython = Get-Command python.exe -ErrorAction SilentlyContinue
    $isStoreShim = $false
    if ($existingPython -and $existingPython.Source -like "*\Microsoft\WindowsApps\*") {
        Write-Log "Found Python Store shim, ignoring..." "WARNING"
        $isStoreShim = $true
    }

    if ($existingPython -and -not $isStoreShim) {
        Write-Log "Python already installed: $($existingPython.Source)" "INFO"
    } else {
        $targetPythonVersion = $PythonVersion
        if (-not $targetPythonVersion) {
            Write-Log "PythonVersion parameter not provided, falling back to 3.14.0" "WARNING"
            $targetPythonVersion = "3.14.0"
        }

        # If version is major.minor (e.g. 3.14), append .0 for Chocolatey (3.14.0).
        $chocoVersion = $targetPythonVersion
        if ($chocoVersion -match '^\d+\.\d+$') { $chocoVersion = "$chocoVersion.0" }

        Install-WithRetry "Python $chocoVersion" {
            choco install python --version "$chocoVersion" -y --no-progress --limit-output
        }

        # Refresh Path to find the newly installed real Python
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                    [System.Environment]::GetEnvironmentVariable("Path", "User")
    }

    if (-not (Get-Command uv.exe -ErrorAction SilentlyContinue)) {
        Install-WithRetry "uv" {
            choco install uv -y --no-progress --limit-output
        }
    }

    if (-not (Get-Command nssm.exe -ErrorAction SilentlyContinue)) {
        Install-WithRetry "NSSM" {
            choco install nssm -y --no-progress --limit-output
        }
    }

    # Refresh PATH one last time to ensure all new binaries are available
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
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
        $response = Invoke-WebRequest -Uri $apiUrl -Headers $headers -UseBasicParsing -ErrorAction Stop
        $release = $response.Content | ConvertFrom-Json
    } catch {
        $rateLimitMsg = ""
        try {
            $resetHeader = $_.Exception.Response.Headers["x-ratelimit-reset"]
            if ($resetHeader) {
                $resetTime = [System.DateTimeOffset]::FromUnixTimeSeconds([long]$resetHeader).ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss")
                $rateLimitMsg = " Rate limit resets at $resetTime (local time)."
            }
        } catch {}
        throw "Could not retrieve release from $apiUrl. If the repo is private, supply -GitHubToken.$rateLimitMsg Error: $_"
    }

    Write-Log "Release found: $($release.tag_name) - $($release.name)" "INFO"

    $zipAsset = $release.assets | Where-Object { $_.name -like "gateway-*.zip" -and $_.name -notlike "*.sha256" } | Select-Object -First 1
    if (-not $zipAsset) {
        throw "No gateway-*.zip asset in release $($release.tag_name). Available: $(($release.assets | ForEach-Object { $_.name }) -join ', ')"
    }

    $shaAsset = $release.assets | Where-Object { $_.name -eq "$($zipAsset.name).sha256" } | Select-Object -First 1

    # Use a unique filename per run to avoid file-lock collisions when concurrent
    # deployments target the same machine (e.g. two pipeline runs in flight).
    $runId = [guid]::NewGuid().ToString().Substring(0, 8)
    $ZipPath = Join-Path $downloadDir "$([System.IO.Path]::GetFileNameWithoutExtension($zipAsset.name))-$runId.zip"
    $downloadHeaders = @{ "Accept" = "application/octet-stream"; "User-Agent" = "Gateway-Deploy-Script" }
    if ($GitHubToken) { $downloadHeaders["Authorization"] = "Bearer $GitHubToken" }

    $sizeMB = [math]::Round($zipAsset.size / 1MB, 1)
    Write-Log "Downloading $($zipAsset.name) ($sizeMB MB)..." "INFO"
    Invoke-WebRequest -Uri $zipAsset.browser_download_url -Headers $downloadHeaders -OutFile $ZipPath -UseBasicParsing -ErrorAction Stop
    Write-Log "Downloaded to $ZipPath" "SUCCESS"

    if ($shaAsset) {
        $shaDownloadPath = "$ZipPath.sha256"
        Invoke-WebRequest -Uri $shaAsset.browser_download_url -Headers $downloadHeaders -OutFile $shaDownloadPath -UseBasicParsing -ErrorAction Stop
        Write-Log "Downloaded checksum" "SUCCESS"
    }
}

# -- Refresh PATH (Chocolatey updates registry but not the running process) ---

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

# Arc Run Command runs as SYSTEM; add the explicit Chocolatey Python path as a fallback.
if ($PythonVersion) {
    $pyMajorMinor = (($PythonVersion -split '\.')[0..1]) -join ''
    $pyPath = "C:\Python$pyMajorMinor"
    if (Test-Path $pyPath) { $env:Path += ";$pyPath" }
}

# -- Validation ---------------------------------------------------------------

$pythonExe = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $pythonExe) { throw "Python not found in PATH. Pass -Bootstrap:`$false to skip bootstrap, or install manually." }

$uvExe = Get-Command uv.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $uvExe) { throw "uv not found in PATH. Pass -Bootstrap:`$false to skip bootstrap, or install manually." }

$nssmExe = Get-Command nssm.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
if (-not $nssmExe) { throw "NSSM not found in PATH. Pass -Bootstrap:`$false to skip bootstrap, or install manually." }

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
if (($Environment -ne "prod") -and ($Environment -ne "preprod")) {
    $services += @{ Name = "Gateway-Emulator"; Script = "modality_emulator.py" }
}

# -- Extraction ---------------------------------------------------------------

$version = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath) -replace 'gateway-', ''
$versionDir = Join-Path $releasesDir $version

Write-Log "Deploying version: $version" "INFO"

# If redeploying the same version, stop services to release .pyd file locks
if (Test-Path $versionDir) {
    Write-Log "Version directory exists. Stopping services to release file locks..." "WARNING"
    Stop-AllServices -Services $services -TimeoutSeconds $ServiceStopTimeoutSeconds
}

$stagingDir = Join-Path $BaseInstallPath "staging-$([guid]::NewGuid().ToString().Substring(0,8))"
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
    $batContent = @(
        '@echo off',
        "cd /d `"$BaseInstallPath`"",
        'set "PYTHONPATH=current\src"',
        ('"current\.venv\Scripts\python.exe" "current\src\' + $svc.Script + '"')
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
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "AppDirectory", "$BaseInstallPath") -Description "set AppDirectory"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "Description", "Manage Breast Screening Gateway - $($svc.Name)") -Description "set Description"
    Invoke-Nssm -NssmPath $nssmExe -Arguments @("set", $svc.Name, "Start", "SERVICE_AUTO_START") -Description "set Start"

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
                & $nssmExe set $svc.Name AppDirectory "$BaseInstallPath" 2>&1 | Out-Null
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

# Record the deployed release tag so subsequent runs can skip reinstallation.
$versionFile = Join-Path $BaseInstallPath "VERSION"
[System.IO.File]::WriteAllText($versionFile, $ReleaseTag, (New-Object System.Text.UTF8Encoding $false))
Write-Log "Written VERSION: $ReleaseTag" "INFO"
