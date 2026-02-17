#Requires -Version 5.1
<#
.SYNOPSIS
    Reset the VM by removing all Gateway and Mock services and directories.
.DESCRIPTION
    Stops and deletes Windows services (using NSSM/sc) and removes installation folders.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Paths = @(
        "C:\Program Files\NHS\ManageBreastScreeningGateway",
        "C:\Apps\DicomGatewayMock"
    ),

    [Parameter()]
    [string[]]$ServicePatterns = @(
        "Gateway-*",
        "DicomGatewayMock"
    )
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue" # Continue on errors to ensure we try to clean everything

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "VM Reset / Cleanup Started" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Identify and Stop Services
foreach ($pattern in $ServicePatterns) {
    $services = Get-Service -Name $pattern -ErrorAction SilentlyContinue
    foreach ($svc in $services) {
        Write-Host "Processing Service: $($svc.Name)" -ForegroundColor Yellow
        
        if ($svc.Status -eq 'Running') {
            Write-Host "  Stopping service..." -ForegroundColor Gray
            Stop-Service -Name $svc.Name -Force -ErrorAction SilentlyContinue
        }

        Write-Host "  Removing service..." -ForegroundColor Gray
        # Try removing with nssm first (if available) as it cleans up registry better
        $nssm = Get-Command nssm.exe -ErrorAction SilentlyContinue
        if ($nssm) {
            & $nssm.Source remove $svc.Name confirm | Out-Null
        } else {
            # Fallback to standard sc.exe
            & sc.exe delete $svc.Name | Out-Null
        }
    }
}

# 2. Remove Installation Directories
foreach ($path in $Paths) {
    if (Test-Path $path) {
        Write-Host "Removing Directory: $path" -ForegroundColor Yellow
        # Junctions can be tricky; remove the 'current' junction first if it exists
        $current = Join-Path $path "current"
        if (Test-Path $current) {
            Write-Host "  Removing junction..." -ForegroundColor Gray
            Remove-Item -Path $current -Force -ErrorAction SilentlyContinue
        }
        
        try {
            Remove-Item -Path $path -Recurse -Force
            Write-Host "  Directory removed successfully." -ForegroundColor Green
        } catch {
            Write-Host "  Warning: Could not remove $path. It may be in use. Check for open shells or log viewers." -ForegroundColor Red
        }
    }
}

# 3. Clean Staging / Temp
$tempStaging = Join-Path $env:TEMP "gateway-deploy-staging-*"
Get-Item $tempStaging -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "`n========================================" -ForegroundColor Green
Write-Host "Cleanup Complete. The VM is ready for a fresh deployment." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
