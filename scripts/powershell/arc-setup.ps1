# Azure Arc evaluation and onboarding script.
# Parameters injected by Terraform via azurerm_virtual_machine_run_command.
param(
    [string]$SubscriptionId,
    [string]$TenantId,
    [string]$ResourceGroup,
    [string]$Location,
    [string]$ServicePrincipalId,
    [string]$ServicePrincipalSecret,
    # Site identity - controls the Arc resource name and Azure tags.
    # SiteCode becomes the Arc machine name in Azure (e.g. gw-RVJ-01).
    # Defaults to the machine hostname when not supplied (test/dev use).
    [string]$SiteCode       = "",       # e.g. gw-RVJ-01 (ODS code + instance)
    [string]$SiteName       = "",       # e.g. North-Bristol-NHS-Trust (no spaces)
    [string]$NHSRegion      = "",       # nw|neyh|mids|eoe|lon|se|sw
    [string]$PacsVendor     = "",       # sectra|fujifilm|agfa|philips|carestream
    [string]$SiteType       = "static", # static|mobile
    [string]$DeploymentRing = "ring0"   # ring0|ring1|ring2|ring3|ring4
)

$ErrorActionPreference = 'Stop'
$logFile = "C:\ArcSetup\ArcSetup.log"

New-Item -Path "C:\ArcSetup" -ItemType Directory -Force | Out-Null

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $logMessage = "[$timestamp] [$Level] $Message"
    Add-Content -Path $logFile -Value $logMessage -Force
    Write-Output $logMessage
}

try {
    Write-Log "=========================================" "INFO"
    Write-Log "Azure Arc Combined Setup Started" "INFO"
    Write-Log "=========================================" "INFO"
    Write-Log "SiteCode       : $(if ($SiteCode) { $SiteCode } else { '(hostname)' })" "INFO"
    Write-Log "SiteName       : $(if ($SiteName) { $SiteName } else { '(not set)' })" "INFO"
    Write-Log "NHSRegion      : $(if ($NHSRegion) { $NHSRegion } else { '(not set)' })" "INFO"
    Write-Log "PacsVendor     : $(if ($PacsVendor) { $PacsVendor } else { '(not set)' })" "INFO"
    Write-Log "SiteType       : $SiteType" "INFO"
    Write-Log "DeploymentRing : $DeploymentRing" "INFO"
    Write-Log "=========================================" "INFO"

    $CorrelationId = [guid]::NewGuid().ToString()

    $env:SUBSCRIPTION_ID = $SubscriptionId
    $env:RESOURCE_GROUP  = $ResourceGroup
    $env:TENANT_ID       = $TenantId
    $env:LOCATION        = $Location
    $env:AUTH_TYPE       = "principal"
    $env:CORRELATION_ID  = $CorrelationId
    $env:CLOUD           = "AzureCloud"

    # ============================================
    # PHASE 1: Azure Arc Evaluation Preparation
    # ============================================
    Write-Log "PHASE 1: Preparing VM for Azure Arc Evaluation" "INFO"
    Write-Log "-------------------------------------------" "INFO"

    Write-Log "STEP 1: Setting MSFT_ARC_TEST environment variable..." "INFO"
    [System.Environment]::SetEnvironmentVariable('MSFT_ARC_TEST', 'true', [System.EnvironmentVariableTarget]::Machine)
    Write-Log "MSFT_ARC_TEST set to 'true'" "SUCCESS"

    Write-Log "STEP 2: Disabling Azure VM Guest Agent..." "INFO"
    $service = Get-Service -Name 'WindowsAzureGuestAgent' -ErrorAction SilentlyContinue
    if ($service) {
        Set-Service WindowsAzureGuestAgent -StartupType Disabled -Verbose
        Stop-Service WindowsAzureGuestAgent -Force -Verbose
        Get-Process -Name 'WindowsAzureGuestAgent', 'WaAppAgent' -ErrorAction SilentlyContinue | Stop-Process -Force
        Start-Sleep -Seconds 3
        $serviceStatus = (Get-Service -Name 'WindowsAzureGuestAgent').Status
        Write-Log "Azure Guest Agent status: $serviceStatus" "SUCCESS"
    } else {
        Write-Log "WindowsAzureGuestAgent service not found" "WARNING"
    }

    Write-Log "STEP 3: Blocking Azure IMDS endpoint (169.254.169.254)..." "INFO" # gitleaks:allow
    $existingRule = Get-NetFirewallRule -Name 'BlockAzureIMDS' -ErrorAction SilentlyContinue
    if ($existingRule) {
        Remove-NetFirewallRule -Name 'BlockAzureIMDS' -Confirm:$false
    }
    New-NetFirewallRule -Name BlockAzureIMDS `
                        -DisplayName "Block access to Azure IMDS" `
                        -Enabled True `
                        -Profile Any `
                        -Direction Outbound `
                        -Action Block `
                        -RemoteAddress 169.254.169.254 | Out-Null # gitleaks:allow
    Write-Log "Azure IMDS endpoint blocked" "SUCCESS"

    Write-Log "STEP 4: Verifying Arc Evaluation readiness..." "INFO"
    try {
        $null = Invoke-RestMethod -Headers @{'Metadata' = 'true' } -Method GET `
            -Uri 'http://169.254.169.254/metadata/instance?api-version=2021-02-01' -TimeoutSec 5 -ErrorAction Stop # gitleaks:allow
        Write-Log "WARNING: IMDS is still accessible - Arc onboarding may fail." "WARNING"
    } catch {
        Write-Log "IMDS is blocked as expected" "SUCCESS"
    }

    Write-Log "Phase 1 completed successfully" "SUCCESS"

    # ============================================
    # PHASE 2: Azure Arc Agent Installation
    # ============================================
    Write-Log "PHASE 2: Installing Azure Arc Agent" "INFO"
    Write-Log "-------------------------------------------" "INFO"

    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072

    $azcmagentPath = Join-Path $env:SystemRoot "AzureConnectedMachineAgent"
    $tempPath      = Join-Path $azcmagentPath "temp"
    New-Item -Path $azcmagentPath -ItemType Directory -Force | Out-Null
    New-Item -Path $tempPath      -ItemType Directory -Force | Out-Null

    $installScriptPath = Join-Path $tempPath "install_windows_azcmagent.ps1"
    Write-Log "Downloading Azure Connected Machine Agent installer..." "INFO"
    Invoke-WebRequest -UseBasicParsing `
        -Uri "https://gbl.his.arc.azure.com/azcmagent-windows" `
        -TimeoutSec 30 -OutFile "$installScriptPath"
    Write-Log "Installer downloaded" "SUCCESS"

    Write-Log "Installing Azure Connected Machine Agent..." "INFO"
    & "$installScriptPath"
    if ($LASTEXITCODE -ne 0) { throw "Installation failed with exit code $LASTEXITCODE" }
    Write-Log "Arc agent installed" "SUCCESS"

    Start-Sleep -Seconds 5

    # ============================================
    # PHASE 3: Azure Arc Agent Connection
    # ============================================
    Write-Log "PHASE 3: Connecting to Azure Arc" "INFO"
    Write-Log "-------------------------------------------" "INFO"

    $azcmagentExe = "$env:ProgramW6432\AzureConnectedMachineAgent\azcmagent.exe"
    if (-Not (Test-Path $azcmagentExe)) { throw "azcmagent.exe not found at $azcmagentExe" }

    Write-Log "Subscription  : $SubscriptionId" "INFO"
    Write-Log "Resource Group: $ResourceGroup" "INFO"
    Write-Log "Location      : $Location" "INFO"

    # Build tags - all site metadata is stamped onto the Arc resource for Terraform
    # discovery and ADO pipeline targeting. SiteName must not contain spaces.
    $tags  = "ArcSQLServerExtensionDeployment=Disabled"
    $tags += " Programme=BreastScreening"
    $tags += " SiteType=$SiteType"
    $tags += " DeploymentRing=$DeploymentRing"
    if ($SiteCode)   { $tags += " SiteCode=$SiteCode" }
    if ($SiteName)   { $tags += " SiteName=$SiteName" }
    if ($NHSRegion)  { $tags += " NHSRegion=$NHSRegion" }
    if ($PacsVendor) { $tags += " PacsVendor=$PacsVendor" }

    # Build connect arguments. --resource-name sets the Azure resource name,
    # overriding the default (hostname). Required for meaningful HC naming in Terraform.
    $connectArgs = @(
        'connect',
        '--service-principal-id',     $ServicePrincipalId,
        '--service-principal-secret', $ServicePrincipalSecret,
        '--resource-group',           $ResourceGroup,
        '--tenant-id',                $TenantId,
        '--location',                 $Location,
        '--subscription-id',          $SubscriptionId,
        '--cloud',                    $env:CLOUD,
        '--correlation-id',           $CorrelationId,
        '--tags',                     $tags
    )
    if ($SiteCode) { $connectArgs += @('--resource-name', $SiteCode) }

    & "$azcmagentExe" @connectArgs

    if ($LASTEXITCODE -ne 0) { throw "Connection failed with exit code $LASTEXITCODE" }
    Write-Log "Successfully connected to Azure Arc!" "SUCCESS"

    # ============================================
    # PHASE 4: Verification
    # ============================================
    Write-Log "PHASE 4: Final Verification" "INFO"
    Write-Log "-------------------------------------------" "INFO"

    try {
        & "$azcmagentExe" show
        Write-Log "Arc agent status retrieved" "SUCCESS"
    } catch {
        Write-Log "Could not retrieve Arc agent status: $($_.Exception.Message)" "WARNING"
    }

    try {
        Unregister-ScheduledTask -TaskName "ArcSetup" -Confirm:$false -ErrorAction SilentlyContinue
        Write-Log "Scheduled task removed" "SUCCESS"
    } catch {
        Write-Log "Could not remove scheduled task: $($_.Exception.Message)" "WARNING"
    }

    # Re-enable Guest Agent so Run Command can report status back to Azure.
    # Arc evaluation posture is preserved: MSFT_ARC_TEST and IMDS firewall block persist.
    Write-Log "Re-enabling Azure VM Guest Agent for Run Command status reporting..." "INFO"
    Set-Service WindowsAzureGuestAgent -StartupType Automatic -ErrorAction SilentlyContinue
    Start-Service WindowsAzureGuestAgent -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 20
    Write-Log "Azure VM Guest Agent re-enabled" "SUCCESS"

    Write-Log "=========================================" "SUCCESS"
    Write-Log "Azure Arc Setup Completed Successfully!" "SUCCESS"
    Write-Log "=========================================" "SUCCESS"
    exit 0

} catch {
    Write-Log "=========================================" "ERROR"
    Write-Log "Azure Arc Setup Failed" "ERROR"
    Write-Log "=========================================" "ERROR"
    Write-Log "Error: $($_.Exception.Message)" "ERROR"
    Write-Log "Stack Trace: $($_.ScriptStackTrace)" "ERROR"

    $logBody = @{
        subscriptionId = "$env:SUBSCRIPTION_ID"
        resourceGroup  = "$env:RESOURCE_GROUP"
        tenantId       = "$env:TENANT_ID"
        location       = "$env:LOCATION"
        correlationId  = "$env:CORRELATION_ID"
        authType       = "$env:AUTH_TYPE"
        operation      = "onboarding"
        messageType    = $_.FullyQualifiedErrorId
        message        = "$_"
    }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "https://gbl.his.arc.azure.com/log" `
            -Method "PUT" -Body ($logBody | ConvertTo-Json) | Out-Null
    } catch {
        Write-Log "Failed to send error log: $($_.Exception.Message)" "WARNING"
    }

    exit 1
}
