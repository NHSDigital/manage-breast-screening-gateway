# Deployment Guide

> **Script**: `scripts/powershell/deploy.ps1`
> **Target OS**: Windows Server (PowerShell 5.1+)
> **Strategy**: Blue/Green with automatic rollback

---

## Prerequisites

The following tools must be available on the target machine. Use the `-Bootstrap` flag to install them automatically via Chocolatey, or install them manually.

| Tool | Purpose |
|------|---------|
| Python 3.14+ | Application runtime |
| [uv](https://docs.astral.sh/uv/) | Python package and virtualenv manager |
| [NSSM](https://nssm.cc/) | Non-Sucking Service Manager for Windows Services |

## Quick Start

### Deploy the latest GitHub release (default)

```powershell
.\scripts\powershell\deploy.ps1
```

This downloads the latest release from `NHSDigital/manage-breast-screening-gateway`, verifies its checksum, and deploys it.

### First-time deployment (bootstraps tools + deploys latest release)

```powershell
.\scripts\powershell\deploy.ps1 -Bootstrap
```

### Deploy a specific release tag

```powershell
.\scripts\powershell\deploy.ps1 -ReleaseTag "v1.2.0"
```

### Deploy from a local package (skip download)

```powershell
.\scripts\powershell\deploy.ps1 -ZipPath "C:\Packages\gateway-1.0.0.zip"
```

When `-ZipPath` is provided, the GitHub download step is skipped entirely.

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `-ZipPath` | string | *(download from GitHub)* | Local path to a deployment archive. When set, skips GitHub download |
| `-GitHubRepo` | string | `NHSDigital/manage-breast-screening-gateway` | GitHub repository in `owner/repo` format |
| `-ReleaseTag` | string | `latest` | GitHub release tag to download (e.g., `v1.2.0`) |
| `-GitHubToken` | string | *(none)* | GitHub personal access token. Required for private repos |
| `-BaseInstallPath` | string | `C:\Program Files\NHS\ManageBreastScreeningGateway` | Root installation directory |
| `-Bootstrap` | switch | `$false` | Install Chocolatey, Python, uv, and NSSM if missing |
| `-PythonVersion` | string | *(from pyproject.toml)* | Override the Python version installed during bootstrap (e.g., `3.14`) |
| `-KeepReleases` | int | `3` | Number of previous release directories to retain |
| `-ServiceStopTimeoutSeconds` | int | `30` | Maximum seconds to wait for each service to stop |
| `-HealthCheckRetries` | int | `5` | Number of post-start health check attempts per service |
| `-HealthCheckIntervalSeconds` | int | `2` | Seconds between health check attempts |

## Directory Layout

After a successful deployment the installation directory has this structure:

```text
C:\Program Files\NHS\ManageBreastScreeningGateway\
  current\               # Junction (symlink) pointing to the active release
  releases\
    1.0.0\               # Versioned release directory
    1.1.0\               # Each contains its own .venv, source, and .bat helpers
  downloads\             # GitHub release artifacts downloaded by the script
  data\                  # Persistent application data (survives upgrades)
  logs\
    deployments\         # Timestamped deployment and rollback log files
    Gateway-Relay.log    # Per-service stdout/stderr captured by NSSM
    Gateway-PACS.log
    Gateway-MWL.log
    Gateway-Upload.log
```

## Windows Services

The script manages four Windows Services via NSSM:

| Service Name | Entry Point | Description |
|--------------|-------------|-------------|
| `Gateway-Relay` | `src/relay_listener.py` | Azure Relay listener for worklist actions |
| `Gateway-PACS` | `src/pacs_main.py` | DICOM PACS server (C-STORE SCP) |
| `Gateway-MWL` | `src/mwl_main.py` | Modality Worklist server (C-FIND SCP) |
| `Gateway-Upload` | `src/upload_main.py` | Image upload processor |

Each service runs via a generated `.bat` wrapper that sets `PYTHONPATH=src` and launches the entry point using the release's own `.venv\Scripts\python.exe`.

All services are registered with `SERVICE_AUTO_START` so they survive reboots. On each deployment, existing services are removed and re-registered from scratch to avoid NSSM throttle state issues from previous failed deployments.

## Package Format

The script accepts two package formats:

1. **Wrapper ZIP** (recommended) -- A ZIP containing an inner application ZIP and its `.sha256` checksum. Both layers are integrity-verified.
2. **Direct ZIP** -- A ZIP containing the application source directly (`pyproject.toml` at root).

The archive filename determines the version string. Expected naming convention:

```
gateway-<version>.zip          # e.g. gateway-1.2.3.zip
gateway-<version>.zip.sha256   # Optional outer checksum
```

The package **must** include both `pyproject.toml` and `uv.lock` at its root (after extraction).

## Integrity Verification

SHA256 checksums are verified at two levels:

1. **Outer archive** -- If a `.sha256` file exists alongside the ZIP, the script verifies the outer archive before extraction.
2. **Inner archive** -- If the wrapper ZIP contains an inner `.sha256` file, the inner application ZIP is verified before final extraction.

If either check fails, the deployment aborts immediately.

## Rollback

The standard process is **fix-forward** -- deploy a corrected version using `deploy.ps1`. For urgent situations, use the standalone rollback script. See the [Rollback Runbook](./runbooks/rollback.md) for full procedures.

`deploy.ps1` also rolls back automatically if any service fails to start or fails its post-start health check.

## Cleanup

To completely reset the VM, see the [Cleanup Runbook](./runbooks/cleanup.md).

## Logs

Every deployment creates a timestamped log file at:

```
<BaseInstallPath>\logs\deployments\deployment-YYYYMMDD-HHmmss.log
```

Rollback operations write to `rollback-YYYYMMDD-HHmmss.log` in the same directory.

Each line includes a timestamp, severity level (`INFO`, `WARNING`, `ERROR`, `SUCCESS`), and message. Check these logs first when troubleshooting.

## Useful Commands

```powershell
# Check which version is currently active
Split-Path (Get-Item "C:\Program Files\NHS\ManageBreastScreeningGateway\current").Target -Leaf

# Check service status
Get-Service Gateway-* | Format-Table Name, Status

# View recent deployment logs
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\logs\deployments" |
    Sort-Object LastWriteTime -Descending | Select-Object -First 5
```

## Examples

### Deploy latest release (simplest)

```powershell
.\scripts\powershell\deploy.ps1
```

### Deploy a specific tagged release

```powershell
.\scripts\powershell\deploy.ps1 -ReleaseTag "v2.0.0"
```

### Deploy from a private repo

```powershell
.\scripts\powershell\deploy.ps1 -GitHubToken $env:GITHUB_TOKEN
```

### Deploy from a local package (skip download)

```powershell
.\scripts\powershell\deploy.ps1 -ZipPath "C:\Packages\gateway-2.0.0.zip"
```

### Bootstrap with explicit Python version

```powershell
.\scripts\powershell\deploy.ps1 -Bootstrap -PythonVersion "3.14"
```

### Deploy with custom health check settings

```powershell
.\scripts\powershell\deploy.ps1 `
    -HealthCheckRetries 10 `
    -HealthCheckIntervalSeconds 5
```

### Keep more release history

```powershell
.\scripts\powershell\deploy.ps1 -KeepReleases 5
```
