# 16. Deploy Script — Step-by-Step Analysis

> **System**: manage-breast-screening-gateway
> **Script**: `scripts/powershell/deploy.ps1`
> **Strategy**: Blue/Green deployment with automatic rollback
> **Cross-references**: [Doc 15 - Deployment & Rollback Runbook](./15-Deployment-Rollback-Runbook.md) | [Doc 7 - DR/Backup](./7-DR-Backup-Strategy.md)

---

## Overview

The deploy script automates the full lifecycle of deploying the Manage Breast Screening Gateway onto a Windows Server VM. By default, it downloads the release package directly from GitHub Releases, with an override to use a local file instead. It follows a blue/green deployment model where a new release is prepared in isolation, services are atomically switched via a filesystem junction, and an automatic rollback is triggered if any service fails to start or crashes shortly after launch.

---

## Step-by-Step Breakdown

### Step 1: Logging Configuration

```text
Lines 49–68
```

**What it does**: Creates a `logs\deployments` directory under the install path and opens a timestamped log file. All subsequent operations write to both the console (colour-coded) and this file.

**Why it matters**: Every deployment leaves a persistent audit trail. If a deployment fails at 2 AM and the operator investigates the next morning, the log file contains the exact sequence of events with millisecond timestamps. The dual-output approach (file + console) means nothing is lost if the terminal session disconnects.

---

### Step 2: Helper Functions

```text
Lines 70–163
```

**What it does**: Defines internal helpers:
- `Invoke-Nssm` — Wraps every NSSM call and checks `$LASTEXITCODE`. Throws immediately with the full command string if NSSM returns a non-zero exit code.
- `Get-PythonVersionFromPyproject` — Parses `requires-python` from `pyproject.toml`.
- `Get-PythonVersionFromZip` — Reads `pyproject.toml` directly from a ZIP archive.
- `Stop-AllServices` — Gracefully stops all components with individual timeout enforcement.

**Why it matters**: NSSM is a native executable and PowerShell does not treat its non-zero exit codes as errors by default. Without explicit checking, a failed `nssm install` or `nssm set` would silently proceed, creating a service that is misconfigured. The helper eliminates this class of bug across all ~12 NSSM invocations.

---

### Step 3: Bootstrap (Optional)

```text
Lines 165–206
```

**What it does**: When `-Bootstrap` is passed, installs Chocolatey (if absent), Python, uv, and NSSM. Each tool is only installed if not already present in PATH. The Python version is resolved from a chain of sources: `-PythonVersion` parameter, local `pyproject.toml`, or `pyproject.toml` read directly from the ZIP archive.

**Why it matters**:
- **Idempotent**: Running bootstrap twice does not reinstall tools that are already present (including Python). This makes the script safe to re-run after a partial failure without triggering Chocolatey "already installed" errors.
- **Dynamic Python version**: Rather than hardcoding a Python version, the script resolves it from a three-level chain: explicit parameter, local `pyproject.toml`, or the `pyproject.toml` inside the deployment archive. This means the packaging pipeline is the single source of truth.
- **Fails fast**: If no version can be determined from any source, the script throws before attempting any installation.

---

### Step 4: Package Acquisition (GitHub Release Download)

```text
Lines 208–258
```

**What it does**: If no `-ZipPath` is provided, the script downloads the release package from GitHub Releases. It queries the GitHub API for the specified release tag (or `latest` by default), locates the `gateway-*.zip` asset and its `.sha256` checksum, and downloads both to a local `downloads` directory under the install path. When `-ZipPath` is provided, this step is skipped entirely.

**Why it matters**:
- **Zero-touch default**: Operators can deploy with a single command (`.\deploy.ps1`) without manually downloading or transferring files. This removes a common source of human error — wrong version, corrupted transfer, or stale artifact.
- **Private repo support**: The optional `-GitHubToken` parameter adds a `Bearer` token to API requests, enabling downloads from private repositories without installing the `gh` CLI on the VM.
- **No external tooling**: Uses `Invoke-RestMethod` and `Invoke-WebRequest`, both built into PowerShell 5.1. No `gh` CLI, `curl`, or `wget` required on the target machine.
- **TLS enforcement**: Explicitly enables TLS 1.2+ before the API call, which is necessary on older Windows Server builds where PowerShell defaults to TLS 1.0.
- **Override escape hatch**: The `-ZipPath` parameter completely bypasses downloading, supporting air-gapped environments, manual testing, or CI pipelines that pre-stage the artifact.

---

### Step 5: Prerequisite Validation

```text
Lines 260–282
```

**What it does**: Verifies that `python.exe`, `uv.exe`, and `nssm.exe` are in PATH, and that `ZipPath` points to an existing file (whether downloaded or provided). If a `.sha256` sidecar file exists, verifies the archive's SHA256 hash.

**Why it matters**:
- **Uses `throw` instead of `exit 1`**: The script uses `throw` for all failures, which is safer than `exit 1`. When a PowerShell script using `exit` is dot-sourced or called from another script, `exit` terminates the entire host process. `throw` propagates an error that the caller can catch with `try/catch`, making the script composable.
- **SHA256 verification**: Catches corrupted downloads or tampered archives before any extraction occurs. This is a defense-in-depth measure against supply chain issues.

---

### Step 6: Directory Structure Preparation

```text
Lines 284–302
```

**What it does**: Ensures the `releases`, `data`, and `logs` directories exist under the base install path.

**Why it matters**: The `data` directory persists across deployments (it is never inside a release folder), so application databases and state survive upgrades. The separation of `releases` (immutable, versioned) from `data` (mutable, persistent) is a core tenet of the blue/green model.

---

### Step 7: Package Extraction

```text
Lines 304–367
```

**What it does**:
1. Extracts the outer ZIP to a temporary staging directory.
2. Looks for an inner ZIP. If found, verifies its SHA256 (if a checksum file is present), then extracts it to the version directory.
3. Falls back to treating the outer ZIP as the application if no inner ZIP exists.
4. Handles nested folder structures (single top-level directory inside the archive).
5. Validates that `pyproject.toml` and `uv.lock` are present in the extracted package.

**Why it matters**:
- **Staging directory**: Extraction happens in `%TEMP%`, not in the install path. If extraction fails, the install directory is untouched. The staging directory is cleaned up in a `finally` block, so it never leaks even on error.
- **Locked file handling**: When re-deploying the same version, the previous release directory may contain locked `.pyd` (native DLL) files from Python packages. The script clears file attributes before removal, preventing "Access denied" errors on compiled extension modules.
- **Double integrity verification**: Both the outer wrapper and the inner application archive can be checksummed independently. This catches corruption at the transport layer and at the packaging layer.
- **`uv.lock` validation**: The subsequent `uv sync --frozen` command requires a lockfile. Without this check, the script would fail with a confusing uv error message deep in the dependency resolution phase. Validating early gives a clear, actionable error.

---

### Step 8: Virtual Environment Setup

```text
Lines 368–390
```

**What it does**: Creates a Python virtual environment inside the version directory using `uv venv`, then installs dependencies with `uv sync --frozen`. After dependency installation, pre-compiles the Python bytecache for both the application source and the standard library. Both external commands check `$LASTEXITCODE` and throw on failure.

**Why it matters**:
- **Isolated per release**: Each release gets its own `.venv`. The previous release's environment is never modified. This is what makes rollback possible — the old environment is still intact.
- **Frozen sync**: `--frozen` means uv installs exactly what is in `uv.lock`, with no resolution. This guarantees the deployed dependencies are identical to what CI tested. No "works on my machine" drift.
- **Bytecache pre-compilation**: Python 3.14 compiles `.pyc` files for the standard library on first import. Without pre-compilation, this happens when services start under NSSM, taking long enough for NSSM to consider the service hung. Running `compileall` during deployment eliminates this first-run penalty.
- **Error propagation**: The `catch` block logs the error and re-throws (not `exit 1`), preserving the call stack for the caller.

---

### Step 9: Service Helper Generation

```text
Lines 392–404
```

**What it does**: Generates `.bat` wrapper scripts for each of the four Gateway services (Relay, PACS, MWL, Upload). Each script sets the working directory, configures `PYTHONPATH=src`, and launches the Python entry point via the release's own virtual environment.

**Why it matters**:
- **`PYTHONPATH=src`**: The entry points (e.g., `pacs_main.py`) import from sibling modules in `src/`. Without setting `PYTHONPATH`, Python cannot resolve these imports when running from the release root directory. This mirrors how the CI smoke test runs.
- **Location-independent**: By using `%~dp0` (the directory of the batch file itself), the scripts work whether accessed via the junction or directly.
- **Isolated environment**: The `.venv\Scripts\python.exe` path ensures the correct per-release virtual environment is always used.

---

### Step 10: Capture Previous Version for Rollback

```text
Lines 411–420
```

**What it does**: Before any destructive action, reads the current junction's target path (if it exists) and stores it in `$previousVersionDir`.

**Why it matters**: This is the safety net. If anything goes wrong during cutover, the script knows exactly where the last known-good release lives. Without this, a failed deployment would leave the system with no path back to a working state.

---

### Step 11: Service Stop with Timeout

```text
Lines 422–423
```

**What it does**: Calls `Stop-AllServices` to gracefully stop each component with individual timeout enforcement. If a timeout is exceeded, the deployment aborts before touching the junction.

**Why it matters**:
- **Graceful shutdown**: Sends a stop signal and gives the service time to finish in-flight DICOM transfers.
- **Abort before damage**: The junction has not been modified yet at this point. If stop fails, the system is still running the old version and no rollback is needed — the deployment simply aborts cleanly.

---

### Step 12: Junction Swap (Atomic Cutover)

```text
Lines 457–458
```

**What it does**: Deletes the old `current` junction and creates a new one pointing to the new version directory.

**Why it matters**: This is the atomic switch. From the perspective of NSSM and all service configurations, `current` is a stable path that never changes — only its target changes. This means services do not need to be reconfigured with new absolute paths on every deployment.

---

### Step 13: Service Registration and Start

```text
Lines 460–495
```

**What it does**: For each service, removes any existing registration and creates a fresh one with NSSM. Configures stdout/stderr logging. Starts each service and tracks which ones were started successfully.

**Why it matters**:
- **Clean registration**: Rather than trying to update existing services in-place, the script removes and re-registers each service on every deployment. This eliminates NSSM's internal "recently crashed" throttle counter that persists from previous failed deployments.
- **SCM synchronisation (Race Condition Protection)**: After removing a service, the script enters a polling loop that queries the Windows Service Control Manager (SCM) until the service is fully deregistered. In Windows, service deletion is asynchronous; attempting to `install` a service immediately after `remove` often fails with "service marked for deletion." This loop guarantees the SCM is ready before the next step.
- **Tracked starts**: `$startedServices` records which services were started. If a failure occurs partway through, only the services that were started are stopped during rollback — avoiding errors from trying to stop services that were never started.
- **Break on first failure**: If any service fails to start, the loop breaks immediately rather than continuing to start services that depend on a broken state.

---

### Step 14: Post-Start Health Checks

```text
Lines 497–519
```

**What it does**: After all services start, polls each one repeatedly (default: 5 attempts, 2s apart) to verify it remains in `Running` state. If a service crashes (e.g., import error, missing config), the health check detects it.

**Why it matters**: `Start-Service` succeeding only means the service control manager accepted the start request. The actual process could crash within milliseconds. The health check window catches:
- Missing Python dependencies despite `uv sync`
- Configuration errors (missing `.env` variables)
- Port conflicts with another process
- Import errors in the application code

Without this check, a deployment that appears successful could leave the gateway fully down.

---

### Step 15: Automatic Rollback

```text
Lines 521–551
```

**What it does**: If either service start or health check failed:
1. Stops all services started in the failed attempt
2. Re-points the junction to the previous release directory
3. Updates NSSM paths to point through the restored junction
4. Restarts all services with the previous version
5. Throws an error so the caller knows the deployment failed

**Why it matters**: This is the core production-readiness guarantee. In a hospital environment, a non-functional gateway means mammography images cannot be transferred. Automatic rollback minimises the window of unavailability from "until an operator notices and acts" to "a few seconds while the script restores the previous version."

If no previous version exists (first-ever deployment), the script logs a clear warning instead of crashing during rollback.

---

### Step 16: Release Cleanup & Deferred Trash

```text
Lines 425–454
```

**What it does**: Before switching the junction, the script identifies old releases to prune (keeping the latest 3). If a directory cannot be deleted because a file is locked (common with `.pyd` native modules or antivirus scans), the script **moves** the directory to a `.trash-<id>` folder. On the *next* deployment, the script first attempts to empty all `.trash` folders.

**Why it matters**:
- **Zero-fail pruning**: Windows filesystem locks often cause "Access Denied" during recursive deletes. By moving locked folders to a "trash" area, the script ensures the primary `releases` directory stays clean and the deployment continues even if an old version is stubborn.
- **Disk management**: Disk space on hospital VMs is finite. Each release contains a full `.venv` which can be hundreds of megabytes. Keeping 3 releases provides:
  - The current running version
  - One previous version (for manual rollback investigation)
  - One additional version for safety margin
- **Strategic timing**: Cleanup happens while services are stopped but before new ones start, maximizing the chance that file locks have been released.

---

## Reliability Properties Summary

| Property | How the Script Achieves It |
|----------|----------------------------|
| **Atomic cutover** | Filesystem junction swap — services always reference `current\`, only the target changes |
| **Automatic rollback** | Previous junction target is captured before cutover; restored if any service fails start or health check |
| **Automated acquisition** | Downloads from GitHub Releases by default; no manual file transfer needed. Supports private repos via token. `-ZipPath` override for air-gapped environments |
| **Integrity verification** | SHA256 checksums verified at both outer and inner archive levels |
| **Bytecache pre-compilation** | Runs `compileall` on source and stdlib after `uv sync`, eliminating Python 3.14's slow first-run `.pyc` compilation that causes NSSM to consider services hung |
| **Idempotent** | Bootstrap skips installed tools (including Python); service registration does clean remove + reinstall to clear NSSM throttle state |
| **Fail-fast** | All validation (prerequisites, archive integrity, `pyproject.toml`, `uv.lock`) happens before any destructive action |
| **Reproducible builds** | `uv sync --frozen` installs exact lockfile versions — no resolution, no drift |
| **Isolated releases** | Each version has its own `.venv` — old releases are never modified, enabling clean rollback |
| **Auditable** | Every operation is written to a timestamped log file with millisecond precision |
| **Composable** | Uses `throw` instead of `exit 1` — safe to call from other scripts, pipelines, or orchestrators |
| **Timeout-protected** | Service stops have configurable deadlines; deployment aborts before cutover if a service won't stop |
| **External tool safety** | Every NSSM invocation checks `$LASTEXITCODE` via `Invoke-Nssm` helper; SCM polling prevents race conditions during service re-installation |
| **Cleanup** | Staging directories are cleaned in `finally` blocks; old releases are pruned with a **deferred trash** system to handle Windows file locks |
| **ASCII-safe** | All script content is pure ASCII, preventing encoding corruption when files are transferred to Windows VMs with non-UTF-8 default encodings |
