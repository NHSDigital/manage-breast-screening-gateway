# Cleanup Runbook

> **Script**: `scripts/powershell/cleanup.ps1`
> **When to use**: Full VM reset for re-provisioning or test environment teardown
> **Destructive**: Yes -- removes all services, releases, data, and logs

---

## When to Use

| Situation | Action |
|-----------|--------|
| Test environment needs a fresh start | **Cleanup** |
| VM is being decommissioned | **Cleanup** |
| Deployment is corrupted beyond repair | **Cleanup**, then redeploy with `-Bootstrap` |
| Normal version upgrade | Use `deploy.ps1` instead -- do NOT clean up |
| Need to revert to a previous version | Use `rollback.ps1` instead -- do NOT clean up |

## What Gets Removed

| Item | Path |
|------|------|
| All `Gateway-*` Windows Services | Service Control Manager |
| All `DicomGatewayMock` services (if present) | Service Control Manager |
| Gateway installation directory | `C:\Program Files\NHS\ManageBreastScreeningGateway` |
| Mock installation directory (if present) | `C:\Apps\DicomGatewayMock` |
| Temporary staging directories | `%TEMP%\gateway-deploy-staging-*` |

The cleanup does **not** remove:
- Chocolatey, Python, uv, or NSSM (installed system-wide)
- Any data outside the installation directories

## Prerequisites

- PowerShell must be running as Administrator
- No open file explorers, log viewers, or shells inside the installation directories

## Procedure

### 1. Confirm intent

This is destructive and cannot be undone. Verify you are on the correct VM:

```powershell
hostname
Get-Service Gateway-* | Format-Table Name, Status
```

### 2. Run cleanup

```powershell
.\scripts\powershell\cleanup.ps1
```

The script will:
1. Stop and remove all matching Windows Services (via NSSM if available, `sc.exe` as fallback)
2. Remove the `current` junction (junctions must be removed before their parent)
3. Remove all installation directories recursively
4. Remove any leftover staging directories in `%TEMP%`

### 3. Verify

```powershell
# No services should remain
Get-Service Gateway-* -ErrorAction SilentlyContinue

# Installation directory should be gone
Test-Path "C:\Program Files\NHS\ManageBreastScreeningGateway"
```

### 4. Redeploy (if needed)

After cleanup, bootstrap and deploy from scratch:

```powershell
.\scripts\powershell\deploy.ps1 -Bootstrap
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-Paths` | string[] | `C:\Program Files\NHS\ManageBreastScreeningGateway`, `C:\Apps\DicomGatewayMock` | Installation directories to remove |
| `-ServicePatterns` | string[] | `Gateway-*`, `DicomGatewayMock` | Service name patterns to stop and remove |

### Custom paths

```powershell
.\scripts\powershell\cleanup.ps1 -Paths "D:\CustomPath\Gateway" -ServicePatterns "Gateway-*"
```

## Troubleshooting

### "Could not remove directory -- it may be in use"

A file inside the directory is locked. Common causes:

1. **Open PowerShell session** inside the directory -- close it and retry
2. **Log viewer** (e.g., `Get-Content -Wait`) has a file open -- close it
3. **Antivirus scan** on `.pyd` files -- wait a moment and retry
4. **Service still running** -- check for orphan processes:

```powershell
Get-Process python* | Where-Object { $_.Path -like "*ManageBreastScreeningGateway*" }
# If found, kill them:
Get-Process python* | Where-Object { $_.Path -like "*ManageBreastScreeningGateway*" } | Stop-Process -Force
# Then retry cleanup
.\scripts\powershell\cleanup.ps1
```

### Services still appear after cleanup

The Service Control Manager can take a few seconds to fully deregister services. Wait and check again:

```powershell
Start-Sleep -Seconds 5
Get-Service Gateway-* -ErrorAction SilentlyContinue
```

If they persist, remove manually:

```powershell
sc.exe delete "Gateway-Relay"
sc.exe delete "Gateway-PACS"
sc.exe delete "Gateway-MWL"
sc.exe delete "Gateway-Upload"
```
