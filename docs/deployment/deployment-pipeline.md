# Deployment Pipeline

> **Scope**: End-to-end flow from a GitHub tag or main-branch push through Azure DevOps pipelines to an Arc Run Command executing on hospital gateway VMs.
> **Related docs**: [Windows Service Deploy](./windows-service-deploy.md) | [Onboard Hospital VM](./runbooks/onboard-hospital-vm.md) | [Rollback Runbook](./runbooks/rollback.md)

---

## 1. Overview

Deploying the gateway application involves two systems working in sequence:

1. **GitHub Actions** — runs CI (lint, test, build), publishes a release artefact to GitHub Releases, and triggers Azure DevOps.
2. **Azure DevOps (ADO)** — authenticates to Azure, discovers the target VMs via Azure Arc, and delivers the deployment to each VM using an Arc Run Command.

The VM itself runs [`scripts/powershell/deploy.ps1`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/powershell/deploy.ps1) (embedded in the Run Command) with no inbound connectivity required — the Azure Arc agent on the VM polls Azure for commands over an outbound HTTPS connection.

---

## 2. Trigger Modes

| Trigger                  | Workflow                    | What happens                                                                                      |
| ------------------------ | --------------------------- | ------------------------------------------------------------------------------------------------- |
| Push a `v*` tag          | `cicd-3-release.yaml`       | Full pipeline: CI → build → publish release → deploy dev → deploy preprod → approval → deploy prod |
| Push to `main`           | `cicd-2-main-branch.yaml`   | CI → deploy latest existing release to dev and preprod (no new build)                            |
| Manual `workflow_dispatch` | `cicd-2-main-branch.yaml` | CI → deploy latest existing release to a chosen environment (`dev`, `preprod`, or `review`)      |

The release tag trigger ([`cicd-3-release.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-3-release.yaml)) is the standard path for production releases. The main-branch trigger ([`cicd-2-main-branch.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-2-main-branch.yaml)) keeps non-release environments up to date on every merge.

---

## 3. CI Stages (GitHub Actions)

All three trigger modes run the same first two stages before diverging.

### Stage 1 — Commit ([`stage-1-commit.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-1-commit.yaml))

Runs secret scanning (gitleaks) and any fast-fail checks. Required before any subsequent stage.

### Stage 2 — Test ([`stage-2-test.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-2-test.yaml))

Runs `make test` (unit tests, integration tests, lint). Required before build and deploy.

### Stage 3 — Build ([`stage-3-build.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-3-build.yaml))

Only runs on tag pushes and PR builds. Performs:

1. Calls [`scripts/bash/package_release.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/package_release.sh) to create `gateway-<version>.zip` from git-tracked files only (`src/`, `pyproject.toml`, `uv.lock`, `README.md`) using `git archive`.
2. Runs a local smoke test: extracts the archive, calls `uv sync --frozen --no-dev`, and imports all four service modules to verify the package is importable — see the smoke-test job in [`stage-3-build.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-3-build.yaml).
3. Publishes a GitHub Release (`gh release create`) with the zip and its SHA256 checksum as release assets — see the release job in [`stage-3-build.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-3-build.yaml).
4. Attests build provenance via `actions/attest-build-provenance` — links the artefact to the specific commit and workflow run.

The version string is derived from the git tag (e.g. `v1.2.3` produces `gateway-v1.2.3.zip`).

### Stage 4 — Deploy ([`stage-4-deploy-env.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-4-deploy-env.yaml))

Runs three jobs in order for each environment:

1. **Deploy infra** — calls [`stage-4-deploy.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-4-deploy.yaml) to run Terraform via ADO.
2. **Deploy app** — calls [`stage-4-deploy-app.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-4-deploy-app.yaml) to deploy the application via ADO.
3. **Smoke test** — calls [`scripts/bash/smoke_test.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/smoke_test.sh) via `az connectedmachine run-command` to verify all services are running on every Arc VM in the environment.

---

## 4. Environment Progression

### Release tag ([`cicd-3-release.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-3-release.yaml))

```text
tag push (v*)
  └─► Stage 1 (commit)
  └─► Stage 2 (test)
  └─► Stage 3 (build → GitHub Release published)
  └─► deploy-dev     (stage-4-deploy-env.yaml, environment: dev)
  └─► deploy-preprod (needs: deploy-dev)
  └─► prod-approval  (needs: deploy-preprod)
  └─► deploy-prod    (needs: prod-approval)
```

The `prod-approval` job in [`cicd-3-release.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-3-release.yaml) uses `environment: prod`, which is GitHub Actions' gate mechanism. It only blocks if required reviewers are configured at **GitHub → Settings → Environments → prod**. Without that configuration it passes immediately. The comment at the top of that file notes: _"Prod requires a manual approval — configure required reviewers in GitHub Settings → Environments → prod before provisioning the prod environment."_

Each environment maps to a GitHub environment of the same name. GitHub environment protection rules (required reviewers, deployment branches) can be configured per environment at **Settings → Environments**.

### Main branch push ([`cicd-2-main-branch.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-2-main-branch.yaml))

```text
push to main
  └─► Stage 1 (commit)
  └─► Stage 2 (test)
  └─► resolve (finds latest published release tag)
  └─► deploy-infra-dev → deploy-app-dev
  └─► deploy-infra-preprod → deploy-app-preprod  (only after dev succeeds)
```

The `resolve` job queries GitHub Releases (`gh release list`) and fails the workflow if no release exists yet — see the `resolve` job in [`cicd-2-main-branch.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-2-main-branch.yaml). This ensures the latest tagged release is always deployed — not the current commit.

---

## 5. Triggering ADO from GitHub Actions

[`stage-4-deploy-app.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-4-deploy-app.yaml) triggers ADO using `az pipelines run`:

```bash
az pipelines run \
  --name "Deploy Gateway App - ${ENVIRONMENT}" \
  --org https://dev.azure.com/nhse-dtos \
  --project "${ADO_PROJECT}" \
  --parameters releaseTag="${RELEASE_TAG}" environment="${ENVIRONMENT}" \
               pool="${ADO_MANAGEMENT_POOL}" githubToken="${GITHUB_TOKEN}" \
  --output tsv --query id
```

The GitHub Actions runner authenticates to Azure using OIDC (`azure/login` action) with credentials stored as GitHub environment secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).

After triggering, [`scripts/bash/wait_ado_pipeline.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/wait_ado_pipeline.sh) polls the ADO run until it completes or fails.

The ADO pool (`ADO_MANAGEMENT_POOL`) comes from `infrastructure/environments/<env>/variables.sh`:

| Environment         | Pool                    |
| ------------------- | ----------------------- |
| `review`, `dev`     | `private-pool-dev-uks`  |
| `preprod`, `prod`   | `private-pool-prod-uks` |

---

## 6. ADO Pipeline Structure

Two ADO pipeline YAML files exist; each is registered once per environment in ADO:

| File                                         | Deploys                  | ADO pipeline names                    |
| -------------------------------------------- | ------------------------ | ------------------------------------- |
| [`.azuredevops/pipelines/deploy.yml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.azuredevops/pipelines/deploy.yml)          | Terraform infrastructure | `Deploy Arc Infrastructure - <env>`   |
| [`.azuredevops/pipelines/deploy-app.yml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.azuredevops/pipelines/deploy-app.yml)      | Gateway application      | `Deploy Gateway App - <env>`          |

Each registration uses its own service connection named `mbsgw-<env>` (e.g. `mbsgw-dev`, `mbsgw-preprod`, `mbsgw-prod`). This scoping means a misconfigured prod credential cannot affect dev.

### Infrastructure pipeline ([`deploy.yml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.azuredevops/pipelines/deploy.yml))

Runs `make ci <env> terraform-apply` via `AzureCLI@2`:

```yaml
task: AzureCLI@2
  inputs:
    azureSubscription: mbsgw-${{ parameters.environment }}
    addSpnToEnvironment: true
    inlineScript: |
      export ARM_TENANT_ID="$tenantId"
      export ARM_CLIENT_ID="$servicePrincipalId"
      export ARM_OIDC_TOKEN="$idToken"
      export ARM_USE_OIDC=true
      make ci ${{ parameters.environment }} terraform-apply
```

### Application pipeline ([`deploy-app.yml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.azuredevops/pipelines/deploy-app.yml))

Runs `make ci <env> deploy-app RELEASE_TAG=<tag>`:

```yaml
task: AzureCLI@2
  inputs:
    azureSubscription: mbsgw-${{ parameters.environment }}
    addSpnToEnvironment: true
    inlineScript: |
      export ARM_TENANT_ID="$tenantId"
      export ARM_CLIENT_ID="$servicePrincipalId"
      export ARM_OIDC_TOKEN="$idToken"
      export ARM_USE_OIDC=true
      export GITHUB_TOKEN="${{ parameters.githubToken }}"
      make ci ${{ parameters.environment }} deploy-app RELEASE_TAG="${{ parameters.releaseTag }}"
```

`make deploy-app` resolves to [`scripts/bash/deploy_stage.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_stage.sh) with `ENV_CONFIG` and `GATEWAY_RINGS` set by the environment target in the [`Makefile`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/Makefile).

---

## 7. Ring-Based Deployment

### Ring configuration

Rings are defined by the `GATEWAY_RINGS` variable — see the [`Makefile`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/Makefile) for the default. To expand rollout, override in the environment's variables file:

```bash
# infrastructure/environments/prod/variables.sh
GATEWAY_RINGS="ring0 ring1 ring2"
```

Only environments in `infrastructure/environments/` are modified — pipeline files are unchanged.

### [`deploy_stage.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_stage.sh)

Loops over rings in order, calling `deploy_arc_ring.sh` for each:

```bash
for RING in $RINGS; do
  scripts/bash/deploy_arc_ring.sh "$ENVIRONMENT" "$RING" "$RELEASE_TAG"
done
```

`set -euo pipefail` is set at the top of [`deploy_stage.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_stage.sh), so a failure in any ring exits immediately and stops subsequent rings from running.

### [`deploy_arc_ring.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_arc_ring.sh)

For each ring:

1. **Discovers Arc machines** by querying the Arc resource group for machines tagged `DeploymentRing == <ring>`.
2. **Gracefully skips** if no machines are found — emits an ADO warning and exits 0. This allows new environments to be deployed before any machines are onboarded.
3. **Reads Application Insights connection string** from the Arc RG; emits a warning if absent, writes an empty string, continues.
4. **Builds the `.env` content** per machine. Contents include relay hostname, hybrid connection name, cloud API endpoint, Application Insights connection string, and DICOM service settings.
5. **Base64-encodes** the `.env` content to safely pass newlines across JSON.
6. **Submits an Arc Run Command** via `az rest PUT` to `Microsoft.HybridCompute/machines/<machine>/runCommands/<name>`. The `deploy.ps1` script is read from disk and embedded directly in `source.script`.
7. **Waits in parallel** for all machines in the ring using [`wait_arc_run_command.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/wait_arc_run_command.sh).

> **Why `az rest` not `az connectedmachine run-command create`?** The CLI extension does not reliably support `protectedParameters` for connected machines. Using `az rest PUT` against the ARM API directly gives full control over the request body and consistent behaviour across CLI versions.

> **Why embed `deploy.ps1` in `source.script` rather than passing it as a parameter?** PowerShell parameters travel on the Windows command line (32,767-char limit). The ~40 KB base64-encoded script would exceed this limit, causing silent 1-second failures. Embedding in `source.script` (ARM limit ~4 MB) avoids this entirely. The local file is read at deploy time via `jq --rawfile` in [`deploy_arc_ring.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_arc_ring.sh).

---

## 8. Arc Run Command Execution

The Run Command is submitted asynchronously. [`scripts/bash/wait_arc_run_command.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/wait_arc_run_command.sh) polls the ARM resource every 20 seconds until it reaches a terminal state, or times out after 1800 seconds (30 minutes):

```bash
PROVISIONING_STATE=$(... '.properties.provisioningState')
EXEC_STATE=$(... '.properties.instanceView.executionState')
# Terminal when provisioningState is Failed/Canceled OR
# executionState is Succeeded/Failed/TimedOut/Canceled
```

`provisioningState: Succeeded` only means ARM accepted the resource. The actual script result is in `instanceView.executionState`. Both are checked — see [`wait_arc_run_command.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/wait_arc_run_command.sh).

The Run Command runs as `SYSTEM` on the VM (`runAsSystem: true`) because NSSM service installation requires elevated privileges. The timeout is set to 1800 seconds at the ARM level — see [`deploy_arc_ring.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/deploy_arc_ring.sh).

---

## 9. VM-Side Deployment ([`deploy.ps1`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/powershell/deploy.ps1))

`deploy.ps1` receives four parameters from the Run Command:

| Parameter      | Source                    | Purpose                                                       |
| -------------- | ------------------------- | ------------------------------------------------------------- |
| `ReleaseTag`   | pipeline                  | GitHub release tag to download (e.g. `v1.2.3`)               |
| `PythonVersion` | `.tool-versions`         | Python version to install via Chocolatey                      |
| `EnvContentB64` | built by `deploy_arc_ring.sh` | Base64-encoded `.env` file contents                  |
| `GitHubToken`  | GitHub Actions token      | Auth for GitHub API rate-limit headers (repo is public; optional) |

### Step 1 — Write `.env`

The base64-decoded `.env` is written to `<BaseInstallPath>\.env` using `New-Object System.Text.UTF8Encoding $false` (no BOM). Writing with a BOM causes python-dotenv to silently corrupt the first variable name; the explicit no-BOM encoding prevents this.

The `.env` is written to the root of the install directory, not inside any versioned release directory. All four services read it from there via `load_dotenv()` with NSSM's `AppDirectory` set to `<BaseInstallPath>`. This means one `.env` is shared across all releases and survives blue/green cutovers.

### Step 2 — Version check (idempotent skip)

If a `VERSION` file already records the same `ReleaseTag`, the script exits 0 immediately. This prevents redundant reinstalls when a main-branch push re-deploys an already-installed version.

### Step 3 — Bootstrap (idempotent)

If `-Bootstrap` is `$true` (the default), the script installs missing tooling via Chocolatey:

| Tool                    | Purpose                                 |
| ----------------------- | --------------------------------------- |
| Chocolatey              | Package manager for Windows             |
| Python (pinned version) | Application runtime                     |
| `uv`                    | Python virtualenv and dependency manager |
| NSSM                    | Windows service wrapper                 |

Each installation is retried up to 3 times with exponential back-off (10s, 20s). The PATH is refreshed from the registry after each install.

Arc Run Commands run as the SYSTEM account, which may not have the Chocolatey path. After bootstrap, the script adds `C:\Python<major><minor>` explicitly.

### Step 4 — Download and verify package

The release zip is downloaded from GitHub Releases using the `ReleaseTag` parameter:

```text
GET https://api.github.com/repos/NHSDigital/manage-breast-screening-gateway/releases/tags/<tag>
→ locates asset matching gateway-*.zip
→ downloads zip + .sha256 to <BaseInstallPath>\downloads\
```

SHA256 is verified at two levels:

1. **Outer archive** — if a `.sha256` file exists alongside the outer zip.
2. **Inner archive** — if the outer zip contains an inner zip with a matching `.sha256`.

### Step 5 — Extract

The archive is extracted to a staging directory, then moved to `<BaseInstallPath>\releases\<version>\`. A flattening step removes single top-level directories from the archive. The presence of `pyproject.toml` and `uv.lock` is verified before proceeding.

### Step 6 — Virtual environment setup

```powershell
uv venv --python <python.exe>
uv sync --frozen
python -m compileall -q src/
```

`uv sync --frozen` installs exact dependency versions from `uv.lock` with no resolution. Python bytecache is pre-compiled to avoid slow first-run compilation under NSSM.

### Step 7 — Generate service `.bat` wrappers

For each of the four services, a `.bat` file is written to the release directory:

```bat
@echo off
cd /d "C:\Program Files\NHS\ManageBreastScreeningGateway"
set "PYTHONPATH=current\src"
"current\.venv\Scripts\python.exe" "current\src\<service>.py"
```

The `cd` target is `$BaseInstallPath` (not the versioned release directory), ensuring `load_dotenv()` finds `.env` in the install root regardless of which release is active.

### Step 8 — Blue/Green cutover

The cutover window is the period when services are stopped. It is minimised by completing all preparation (download, extract, venv) before stopping services.

1. Record the current junction target for potential rollback.
2. Stop all four services (`Stop-AllServices`).
3. Remove old releases beyond the `KeepReleases` limit (default: 3) while services are stopped to avoid `.pyd` file locks.
4. Delete the `current` junction and recreate it pointing to the new release directory.
5. Remove and re-register each Windows service via NSSM (to clear throttle state).
6. Start each service and run health checks.

### Step 9 — Health checks

After each service starts, the script polls its status up to `HealthCheckRetries` times (default: 5) at `HealthCheckIntervalSeconds` intervals (default: 2s). If any service is not `Running` within the retries, the deployment fails and triggers automatic rollback.

### Step 10 — Automatic rollback

If any service fails to start or fails health checks:

1. Stop all started services.
2. Switch the `current` junction back to the previous release directory.
3. Update NSSM service registrations to point at the previous release's `.bat` files.
4. Start all services from the previous release.
5. Throw an exception — Arc Run Command exits non-zero, failing the pipeline.

If no previous version exists (first-ever deployment), rollback is skipped and services are left stopped.

### Step 11 — Record version

On success, write the `ReleaseTag` to `<BaseInstallPath>\VERSION`. This is read on the next deployment to detect idempotent re-runs.

---

## 10. Post-Deployment Smoke Test

After the app deployment job completes, [`stage-4-deploy-env.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/stage-4-deploy-env.yaml) runs a smoke test. The test calls [`scripts/bash/smoke_test.sh`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/bash/smoke_test.sh) `<environment>`, which:

1. Lists all Arc machines in the environment's Arc RG.
2. For each machine, submits an `az connectedmachine run-command create` running [`scripts/powershell/smoke_test.ps1`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/scripts/powershell/smoke_test.ps1).
3. Polls up to 5 minutes for completion.
4. Cleans up the run command resource regardless of outcome.
5. Reports failures and exits non-zero if any machine failed.

The smoke test verifies that all four Windows services are in the `Running` state on each machine. It does not test functional DICOM or relay behaviour.

---

## 11. Directory Layout on the VM

```text
C:\Program Files\NHS\ManageBreastScreeningGateway\
  .env                          # Shared config written on every deployment
  VERSION                       # Currently deployed release tag
  current\                      # Junction pointing to active release
  releases\
    v1.0.0\                     # Versioned release directory
      src\                      # Application source
      .venv\                    # Virtual environment (uv sync --frozen)
      pyproject.toml
      uv.lock
      start-Gateway-Relay.bat   # NSSM service launcher
      start-Gateway-PACS.bat
      start-Gateway-MWL.bat
      start-Gateway-Upload.bat
    v1.1.0\                     # Previous release (kept for rollback)
    v1.2.0\                     # Previous release (kept for rollback)
  downloads\                    # Cached GitHub release artefacts
  data\
    pacs.db                     # SQLite — stored DICOM instances
    worklist.db                 # SQLite — worklist items
    storage\                    # DICOM image files (hash-based layout)
  logs\
    deployments\                # Timestamped deployment logs
    Gateway-Relay.log           # Service stdout/stderr (captured by NSSM)
    Gateway-PACS.log
    Gateway-MWL.log
    Gateway-Upload.log
```

The `data/` and `logs/` directories are outside the versioned release tree and survive blue/green cutovers.

---

## 12. Pipeline Identities and Permissions

### GitHub Actions → Azure

GitHub Actions authenticates to Azure using OIDC (no long-lived secrets). The `azure/login` action exchanges a GitHub-issued JWT for a short-lived Azure access token. Three secrets are required per GitHub environment:

| Secret                  | Value                                                   |
| ----------------------- | ------------------------------------------------------- |
| `AZURE_CLIENT_ID`       | Client ID of the ADO-managed identity registered in Entra |
| `AZURE_TENANT_ID`       | NHS Entra tenant ID                                     |
| `AZURE_SUBSCRIPTION_ID` | Target Azure subscription ID                            |

The GitHub Actions identity needs only enough permission to call `az pipelines run` — it does not access Azure resources directly.

### ADO → Azure (per environment)

Each ADO pipeline stage uses an `AzureCLI@2` task with a service connection (`mbsgw-<env>`). The service connection uses OIDC (`ARM_USE_OIDC=true`), injecting `tenantId`, `servicePrincipalId`, and `idToken` into the pipeline shell environment via `addSpnToEnvironment: true`.

The ADO managed identity holds:

| Permission                                          | Scope             | Purpose                                                               |
| --------------------------------------------------- | ----------------- | --------------------------------------------------------------------- |
| `Contributor`                                       | Spoke subscription | Create/update Arc infrastructure and read Terraform state storage    |
| `Key Vault Secrets User`                            | Arc RG Key Vault  | Read cloud API tokens                                                 |
| `Microsoft.HybridCompute/machines/runCommands/write` | Arc RG           | Submit Arc Run Commands                                               |
| `Microsoft.HybridCompute/machines/runCommands/read`  | Arc RG           | Poll Run Command status                                               |

The managed identity does **not** hold `Key Vault Secrets Officer` — it cannot write secrets. Cloud API tokens must be provisioned separately by the team managing the cloud application.

### Separation of environments

Each environment (`dev`, `preprod`, `prod`) has its own:

- ADO service connection scoped to its Azure subscription
- GitHub environment with its own secrets and optional protection rules
- Separate Arc resource group

A failure or compromise in one environment's credentials cannot escalate to another.

---

## 13. Useful Commands

### Check which version is running on a VM

```powershell
Get-Content "C:\Program Files\NHS\ManageBreastScreeningGateway\VERSION"
```

### Check service status

```powershell
Get-Service Gateway-* | Format-Table Name, Status
```

### Tail the most recent deployment log

```powershell
Get-ChildItem "C:\Program Files\NHS\ManageBreastScreeningGateway\logs\deployments" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1 |
    ForEach-Object { Get-Content $_.FullName }
```

### Manually trigger a deployment to a single environment (via ADO)

From a developer machine with ADO CLI access:

```bash
az pipelines run \
  --name "Deploy Gateway App - dev" \
  --org https://dev.azure.com/nhse-dtos \
  --project manage-breast-screening-gateway \
  --parameters releaseTag="v1.2.3" environment="dev" \
               pool="private-pool-dev-uks" githubToken=""
```

### Deploy a specific release tag via GitHub Actions (manual dispatch)

Trigger [`cicd-2-main-branch.yaml`](https://github.com/NHSDigital/manage-breast-screening-gateway/blob/main/.github/workflows/cicd-2-main-branch.yaml) with `workflow_dispatch` targeting `dev` or `preprod`. This deploys the latest _published_ release — not the dispatched tag. To deploy a specific version, use the ADO pipeline directly (see above).
