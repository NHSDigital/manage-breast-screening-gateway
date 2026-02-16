# Rollback Runbook

> **Script**: `scripts/powershell/rollback.ps1`
> **When to use**: Production incident where the current version must be replaced immediately
> **Expected duration**: Under 30 seconds

---

## Decision: Fix-Forward vs Rollback

| Situation | Action |
|-----------|--------|
| Bug found in testing before it reaches users | Fix-forward -- deploy a corrected version |
| Non-critical issue in production | Fix-forward -- deploy a corrected version |
| Production is down or degraded, fix is not ready | **Rollback** |
| Service crashes immediately after deployment | **Rollback** |

Rollback is the emergency path. The standard process is always fix-forward.

## Prerequisites

- The target version must exist in `<BaseInstallPath>\releases\`
- NSSM must be available in PATH
- PowerShell must be running as Administrator

## Procedure

### 1. Check current state

```powershell
# Which version is running?
Split-Path (Get-Item "C:\Program Files\NHS\ManageBreastScreeningGateway\current").Target -Leaf

# Are services running?
Get-Service Gateway-* | Format-Table Name, Status

# What versions are available?
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\releases" -Directory |
    Sort-Object CreationTime -Descending |
    Format-Table Name, CreationTime
```

### 2. Execute rollback

**Roll back to the most recent previous version (default):**

```powershell
.\scripts\powershell\rollback.ps1
```

**Roll back to a specific version:**

```powershell
.\scripts\powershell\rollback.ps1 -Version "1.2.0"
```

The script will:
1. Identify the current active version
2. Validate the target release has `pyproject.toml` and service `.bat` helpers
3. Stop all running services (with timeout enforcement)
4. Switch the `current` junction to the target release
5. Re-register all services via NSSM (clears throttle state)
6. Start all services
7. Run health checks to confirm services are stable

### 3. Verify

```powershell
# Confirm the active version changed
Split-Path (Get-Item "C:\Program Files\NHS\ManageBreastScreeningGateway\current").Target -Leaf

# Confirm all services are running
Get-Service Gateway-* | Format-Table Name, Status
```

### 4. Review logs

```powershell
# Open the rollback log
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\logs\deployments\rollback-*" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 1 |
    ForEach-Object { Get-Content $_.FullName }
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-Version` | string | *(most recent previous)* | Specific release version to roll back to |
| `-BaseInstallPath` | string | `C:\Program Files\NHS\ManageBreastScreeningGateway` | Root installation directory |
| `-ServiceStopTimeoutSeconds` | int | `30` | Maximum seconds to wait for each service to stop |
| `-HealthCheckRetries` | int | `5` | Number of post-start health check attempts |
| `-HealthCheckIntervalSeconds` | int | `2` | Seconds between health check attempts |

## Automatic Rollback (during deployment)

`deploy.ps1` triggers an automatic rollback if:

- Any service fails to start during cutover
- Any service fails the post-start health check (crashes within the check window)

The automatic rollback:
1. Stops all services started in the failed attempt
2. Re-points the `current` junction to the previous release
3. Updates NSSM service paths
4. Restarts all services with the previous version

No manual intervention is needed. Check the deployment log for details.

## Troubleshooting

### "No previous version available for rollback"

Only the current version exists in `releases\`. Either this is the first deployment, or old releases were cleaned up. You need to redeploy a known-good version using `deploy.ps1`.

### "Version 'X' not found"

The specified version directory does not exist. List available versions:

```powershell
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\releases" -Directory
```

### "Service did not stop within timeout"

A service is hung. Increase the timeout or force-kill manually:

```powershell
# Retry with longer timeout
.\scripts\powershell\rollback.ps1 -ServiceStopTimeoutSeconds 120

# Or kill the process manually, then retry
Get-Process python* | Where-Object { $_.Path -like "*ManageBreastScreeningGateway*" } | Stop-Process -Force
.\scripts\powershell\rollback.ps1
```

### "NSSM install failed"

NSSM could not register the service. Check that the `.bat` helper files exist in the target release:

```powershell
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\releases\<version>\start-Gateway-*.bat"
```

If missing, the release is incomplete. Deploy a fresh version instead.

### Health check fails after rollback

The rolled-back version may have a configuration issue (missing `.env` variables, port conflict). Check the service log:

```powershell
Get-Content "C:\Program Files\NHS\ManageBreastScreeningGateway\logs\Gateway-<ServiceName>.log" -Tail 50
```
