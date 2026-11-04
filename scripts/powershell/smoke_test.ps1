#Requires -Version 5.1
<#
.SYNOPSIS
    Smoke test for the gateway services.
.DESCRIPTION
    Checks all 4 Windows services are Running.
    Seeds a test worklist item on the MWL server and verifies it can be found via C-FIND.
    Sends a test DICOM image to the PACS server via C-STORE.
    Verifies the DICOM image upload was attempted.
    Executed on the Arc-enabled VM via az connectedmachine run-command.
#>

$ErrorActionPreference = 'Stop'

Write-Output "=== Gateway Smoke Test ==="

# -- Service check ------------------------------------------------------------

$serviceNames = 'Gateway-PACS', 'Gateway-MWL', 'Gateway-Upload', 'Gateway-Relay'
foreach ($name in $serviceNames) {
    $svc = Get-Service -Name $name -ErrorAction Stop
    if ($svc.Status -ne 'Running') {
        throw "Service $name is not running (status: $($svc.Status))"
    }
    Write-Output "OK: $name is Running"
}

# -- DICOM C-FIND and C-STORE -------------------------------------------------

$installPath = 'C:\Program Files\NHS\ManageBreastScreeningGateway\current'
if (-not (Test-Path $installPath)) {
    throw "Gateway install path not found: $installPath"
}

Set-Location $installPath
$env:PYTHONPATH = 'src'

& '.venv\Scripts\pytest.exe' 'scripts\python\smoke_test.py'
if ($LASTEXITCODE -ne 0) {
    throw "DICOM C-FIND and C-STORE smoke test failed (exit code: $LASTEXITCODE)"
}

Write-Output "=== Smoke test passed ==="
