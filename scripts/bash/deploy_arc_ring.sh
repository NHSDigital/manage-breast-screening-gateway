#!/bin/bash
# Deploy the gateway app to all Arc machines matching a ring within an environment.
# Called by deploy_stage.sh — ARM credentials and terraform outputs are passed in.
#
# Usage: deploy_arc_ring.sh <environment> <ring> <release_tag> \
#                           <relay_namespace> <sas_keys_json> <kv_name>

set -euo pipefail

ENVIRONMENT=$1
RING=$2
RELEASE_TAG=$3
RELAY_NAMESPACE=$4
SAS_KEYS_JSON=$5
KV_NAME=$6

APP_SHORT_NAME="mbsgw"
ARC_RG="rg-${APP_SHORT_NAME}-${ENVIRONMENT}-uks-arc-enabled-servers"
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

  # Relay SAS key for this machine (from Terraform outputs)
  SAS_KEY=$(echo "$SAS_KEYS_JSON" | jq -r --arg m "$MACHINE" '.[$m] // ""')
  [[ -z "$SAS_KEY" ]] && \
    echo "##vso[task.logissue type=warning]No relay SAS key found for $MACHINE in Terraform outputs — relay listener will not connect"

  # Cloud API secrets are optional — warn if absent, services still start
  CLOUD_API_ENDPOINT=$(az keyvault secret show --vault-name "$KV_NAME" \
    --name "cloud-api-endpoint" --query value -o tsv 2>/dev/null || echo "")
  CLOUD_API_TOKEN=$(az keyvault secret show --vault-name "$KV_NAME" \
    --name "cloud-api-token-${MACHINE}" --query value -o tsv 2>/dev/null || echo "")

  [[ -z "$CLOUD_API_ENDPOINT" ]] && \
    echo "##vso[task.logissue type=warning]cloud-api-endpoint not in $KV_NAME — Upload service will not reach cloud API for $MACHINE"
  [[ -z "$CLOUD_API_TOKEN" ]] && \
    echo "##vso[task.logissue type=warning]cloud-api-token-${MACHINE} not in $KV_NAME — Upload service will not authenticate for $MACHINE"

  # Build .env, then base64-encode to safely pass newlines as a protected parameter
  ENV_CONTENT="AZURE_RELAY_NAMESPACE=${RELAY_NAMESPACE}
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
  # Passed as the run command script — protectedParameters keep secrets out of logs.
  read -r -d '' DEPLOY_SCRIPT << 'PSEOF' || true
param([string]$EnvContentB64, [string]$ReleaseTag, [string]$PythonVersion)
$ErrorActionPreference = 'Stop'
$Base = "C:\Program Files\NHS\ManageBreastScreeningGateway"
New-Item -Path $Base -ItemType Directory -Force | Out-Null
$envBytes = [System.Convert]::FromBase64String($EnvContentB64)
$envContent = [System.Text.Encoding]::UTF8.GetString($envBytes)
[System.IO.File]::WriteAllText("$Base\.env", $envContent, [System.Text.Encoding]::UTF8)
Write-Output "Written .env to $Base"
$dst = "$env:TEMP\deploy.ps1"
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/NHSDigital/manage-breast-screening-gateway/main/scripts/powershell/deploy.ps1" -OutFile $dst -UseBasicParsing
Write-Output "Downloaded deploy.ps1"
& $dst -Bootstrap -ReleaseTag $ReleaseTag -BaseInstallPath $Base -PythonVersion $PythonVersion
PSEOF

  # Delete any previous deploy run command (idempotent re-runs)
  az connectedmachine run-command delete \
    --resource-group "$ARC_RG" \
    --machine-name "$MACHINE" \
    --run-command-name "deploy-gateway-app" \
    --yes 2>/dev/null || true

  # Submit via REST API — CLI does not reliably support protectedParameters
  BODY=$(jq -n \
    --arg loc    "$LOCATION" \
    --arg script "$DEPLOY_SCRIPT" \
    --arg tag    "$RELEASE_TAG" \
    --arg pyver  "$PYTHON_VERSION" \
    --arg envb64 "$ENV_CONTENT_B64" \
    '{
      location: $loc,
      properties: {
        source: { script: $script },
        parameters: [
          { name: "ReleaseTag",     value: $tag   },
          { name: "PythonVersion",  value: $pyver }
        ],
        protectedParameters: [
          { name: "EnvContentB64", value: $envb64 }
        ],
        runAsSystem:      true,
        timeoutInSeconds: 1800
      }
    }')

  PUT_RESPONSE=$(az rest --method PUT \
    --url "https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${ARC_RG}/providers/Microsoft.HybridCompute/machines/${MACHINE}/runCommands/deploy-gateway-app?api-version=2024-07-10" \
    --body "$BODY" \
    --output json)
  echo "Run command submitted: $(echo "$PUT_RESPONSE" | jq -r '.properties.provisioningState // "unknown"')"

  scripts/bash/wait_arc_run_command.sh "$MACHINE" "$ARC_RG" "deploy-gateway-app" || FAILED=1
  [[ $FAILED -eq 1 ]] && echo "ERROR: Deploy failed for $MACHINE" && break

done < <(echo "$MACHINES_JSON" | jq -c '.[]')

exit $FAILED
