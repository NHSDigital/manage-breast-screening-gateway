#!/bin/bash
# Deploy the gateway app to all Arc machines matching a ring within an environment.
# Called by deploy_stage.sh.
#
# Usage: deploy_arc_ring.sh <environment> <ring> <release_tag> <kv_name>

set -euo pipefail

ENVIRONMENT=$1
RING=$2
RELEASE_TAG=$3
KV_NAME=$4

APP_SHORT_NAME="mbsgw"
ARC_RG="rg-${APP_SHORT_NAME}-${ENVIRONMENT}-uks-arc-enabled-servers"

# Relay namespace is owned by dtos-manage-breast-screening; derive from environment name.
RELAY_NAMESPACE_NAME="relay-manbrs-${ENVIRONMENT}"
RELAY_RG="rg-manbrs-${ENVIRONMENT}-uks"
RELAY_NAMESPACE_HOSTNAME="${RELAY_NAMESPACE_NAME}.servicebus.windows.net"

# Use forward slashes — Python handles these fine on Windows and avoids .env escaping issues
BASE_PATH="C:/Program Files/NHS/ManageBreastScreeningGateway"
PYTHON_VERSION=$(awk '/^python / {print $2}' .tool-versions)

echo "--- Ring: ${RING} | Environment: ${ENVIRONMENT} | Release: ${RELEASE_TAG} ---"

# ── Discover machines ──────────────────────────────────────────────────────────
MACHINES_JSON=$(az connectedmachine list \
  --resource-group "$ARC_RG" \
  --query "[?tags.DeploymentRing=='${RING}'].{name:name,location:location}" \
  --output json)

MACHINE_COUNT=$(echo "$MACHINES_JSON" | jq 'length')
if [[ "$MACHINE_COUNT" -eq 0 ]]; then
  echo "##vso[task.logissue type=warning]No machines found for ${RING} in ${ENVIRONMENT} — skipping"
  exit 0
fi

echo "Found ${MACHINE_COUNT} machine(s) for ${RING} in ${ENVIRONMENT}"

SUB_ID=$(az account show --query id -o tsv)
FAILED=0

while IFS= read -r MACHINE_JSON; do
  MACHINE=$(echo "$MACHINE_JSON" | jq -r '.name')
  LOCATION=$(echo "$MACHINE_JSON" | jq -r '.location')
  echo "Deploying to $MACHINE ($LOCATION)..."

  # Fetch relay SAS key directly — Contributor includes listKeys on relay HCs,
  # and this avoids any dependency on Terraform state having the resource imported.
  SAS_KEY=$(az relay hyco authorization-rule keys list \
    --resource-group "$RELAY_RG" \
    --namespace-name "$RELAY_NAMESPACE_NAME" \
    --hybrid-connection-name "hc-${MACHINE}" \
    --name listen \
    --query primaryKey -o tsv 2>/dev/null || echo "")
  [[ -z "$SAS_KEY" ]] && \
    echo "##vso[task.logissue type=warning]No relay SAS key found for hc-${MACHINE} — relay listener will not connect"

  # Cloud API secrets are optional — warn if absent, services still start
  CLOUD_API_ENDPOINT=$(az keyvault secret show --vault-name "$KV_NAME" \
    --name "cloud-api-endpoint" --query value -o tsv 2>/dev/null || echo "")
  CLOUD_API_TOKEN=$(az keyvault secret show --vault-name "$KV_NAME" \
    --name "cloud-api-token-${MACHINE}" --query value -o tsv 2>/dev/null || echo "")

  [[ -z "$CLOUD_API_ENDPOINT" ]] && \
    echo "##vso[task.logissue type=warning]cloud-api-endpoint not in $KV_NAME — Upload service will not reach cloud API for $MACHINE"
  [[ -z "$CLOUD_API_TOKEN" ]] && \
    echo "##vso[task.logissue type=warning]cloud-api-token-${MACHINE} not in $KV_NAME — Upload service will not authenticate for $MACHINE"

  # Build .env, then base64-encode to pass newlines as a run command parameter.
  # NOTE: Arc Run Command drops protectedParameters for inline source.script,
  # so EnvContentB64 travels as a regular parameter (base64-encoded, not plain text).
  # TODO: migrate to Key Vault + Arc MSI for production environments.
  ENV_CONTENT="AZURE_RELAY_NAMESPACE=${RELAY_NAMESPACE_HOSTNAME}
AZURE_RELAY_HYBRID_CONNECTION=hc-${MACHINE}
AZURE_RELAY_KEY_NAME=listen
AZURE_RELAY_SHARED_ACCESS_KEY=${SAS_KEY}
CLOUD_API_ENDPOINT=${CLOUD_API_ENDPOINT}
CLOUD_API_TOKEN=${CLOUD_API_TOKEN}
MWL_AET=SCREENING_MWL
MWL_PORT=4243
MWL_DB_PATH=${BASE_PATH}/data/worklist.db
PACS_AET=SCREENING_PACS
PACS_PORT=4244
PACS_STORAGE_PATH=${BASE_PATH}/data/storage
PACS_DB_PATH=${BASE_PATH}/data/pacs.db
LOG_LEVEL=INFO"

  ENV_CONTENT_B64=$(printf '%s' "$ENV_CONTENT" | base64 -w 0)

  # PowerShell: decode .env, write it, download deploy.ps1 from GitHub, run it.
  read -r -d '' DEPLOY_SCRIPT << 'PSEOF' || true
param([string]$EnvContentB64, [string]$ReleaseTag, [string]$PythonVersion)
$ErrorActionPreference = 'Stop'
$Base = "C:\Program Files\NHS\ManageBreastScreeningGateway"
New-Item -Path $Base -ItemType Directory -Force | Out-Null
$envBytes = [System.Convert]::FromBase64String($EnvContentB64)
$envContent = [System.Text.Encoding]::UTF8.GetString($envBytes)
[System.IO.File]::WriteAllText("$Base\.env", $envContent, [System.Text.Encoding]::UTF8)
Write-Output "Written .env to $Base"
# Refresh PATH from registry and add the Chocolatey Python install path explicitly.
# Arc Run Command runs as SYSTEM whose PATH may not include Python even after install,
# because Chocolatey adds it to the installing user's PATH, not SYSTEM's.
# Child processes (deploy.ps1) inherit this updated PATH.
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")
$pyMajorMinor = (($PythonVersion -split '\.')[0..1]) -join ''
$pyPath = "C:\Python$pyMajorMinor"
if (Test-Path $pyPath) { $env:Path += ";$pyPath" }
$dst = "$env:TEMP\deploy.ps1"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NHSDigital/manage-breast-screening-gateway/$ReleaseTag/scripts/powershell/deploy.ps1" -OutFile $dst -UseBasicParsing
Write-Output "Downloaded deploy.ps1 (line count: $((Get-Content $dst).Count))"
& $dst -Bootstrap -ReleaseTag $ReleaseTag -BaseInstallPath $Base -PythonVersion $PythonVersion
PSEOF

  # Delete any previous run command so the PUT is a clean create (idempotent re-runs).
  az rest --method DELETE \
    --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${ARC_RG}/providers/Microsoft.HybridCompute/machines/${MACHINE}/runCommands/deploy-gateway-app?api-version=2024-07-10" \
    2>/dev/null || true
  sleep 5

  # Build parameters JSON for the run command.
  PARAMS_JSON=$(jq -n \
    --arg tag    "$RELEASE_TAG" \
    --arg pyver  "$PYTHON_VERSION" \
    --arg envb64 "$ENV_CONTENT_B64" \
    '[
      {"name": "ReleaseTag",    "value": $tag},
      {"name": "PythonVersion", "value": $pyver},
      {"name": "EnvContentB64", "value": $envb64}
    ]')

  # Delete any previous run command so the create is clean (idempotent re-runs).
  az rest --method DELETE \
    --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${ARC_RG}/providers/Microsoft.HybridCompute/machines/${MACHINE}/runCommands/deploy-gateway-app?api-version=2024-07-10" \
    2>/dev/null || true
  sleep 5

  # az connectedmachine run-command create follows the ARM LRO pattern and blocks
  # until the script completes (or times out), returning the final instanceView.
  echo "Submitting run command for $MACHINE..."
  RESULT=$(az connectedmachine run-command create \
    --resource-group "$ARC_RG" \
    --machine-name "$MACHINE" \
    --name "deploy-gateway-app" \
    --location "$LOCATION" \
    --script "$DEPLOY_SCRIPT" \
    --parameters "$PARAMS_JSON" \
    --run-as-system true \
    --timeout-in-seconds 1800 \
    --output json) || { echo "ERROR: Run command submission failed for $MACHINE"; FAILED=1; break; }

  EXIT_CODE=$(echo "$RESULT"   | jq -r '.properties.instanceView.exitCode // -1')
  OUTPUT=$(echo "$RESULT"      | jq -r '.properties.instanceView.output // ""')
  ERROR_OUT=$(echo "$RESULT"   | jq -r '.properties.instanceView.errorOutput // ""')
  EXEC_STATE=$(echo "$RESULT"  | jq -r '.properties.instanceView.executionState // "Unknown"')

  [[ -n "$OUTPUT"    ]] && echo "=== Script output ===" && echo "$OUTPUT"
  [[ -n "$ERROR_OUT" ]] && echo "=== Script error ===" && echo "$ERROR_OUT"
  echo "Execution state: $EXEC_STATE | Exit code: $EXIT_CODE"

  if [[ "$EXEC_STATE" != "Succeeded" || "$EXIT_CODE" != "0" ]]; then
    echo "ERROR: Deploy failed for $MACHINE (state=$EXEC_STATE, exitCode=$EXIT_CODE)"
    echo "=== Full instanceView ==="
    echo "$RESULT" | jq '.properties.instanceView'
    FAILED=1
    break
  fi

  echo "Deploy succeeded for $MACHINE"

done < <(echo "$MACHINES_JSON" | jq -c '.[]')

exit $FAILED
