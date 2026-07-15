#!/bin/bash
# Deploy the gateway app to all Arc machines matching a ring within an environment.
# Called by deploy_stage.sh.
#
# Usage: deploy_arc_ring.sh <environment> <ring> <release_tag>

set -euo pipefail

ENVIRONMENT=$1
RING=$2
RELEASE_TAG=$3

APP_SHORT_NAME="mbsgw"
ARC_RG="rg-${APP_SHORT_NAME}-${ENVIRONMENT}-uks-arc-enabled-servers"

RELAY_NAMESPACE_HOSTNAME="relay-manbrs-${ENVIRONMENT}.servicebus.windows.net"

# Use forward slashes — Python handles these fine on Windows and avoids .env escaping issues
BASE_PATH="C:/Program Files/NHS/ManageBreastScreeningGateway"
PYTHON_VERSION=$(awk '/^python / {print $2}' .tool-versions)

echo "--- Ring: ${RING} | Environment: ${ENVIRONMENT} | Release: ${RELEASE_TAG} ---"

# ── Per-environment config ─────────────────────────────────────────────────────
source "infrastructure/environments/${ENVIRONMENT}/variables.sh"
CLOUD_API_ENDPOINT="https://${CLOUD_API_HOSTNAME}/api/v1/dicom"

CLOUD_API_RESOURCE=$(az ad sp list \
  --display-name "spn-manbrs-web-api-${ENVIRONMENT}" \
  --query "[0].appId" -o tsv 2>/dev/null || echo "")
if [[ -z "$CLOUD_API_RESOURCE" ]]; then
  echo "##vso[task.logissue type=error]Could not resolve client ID for spn-manbrs-web-api-${ENVIRONMENT}"
  exit 1
fi

APPLICATIONINSIGHTS_CONNECTION_STRING=$(az monitor app-insights component show \
  --app "ai-${APP_SHORT_NAME}-${ENVIRONMENT}-arc-uks" \
  --resource-group "$ARC_RG" \
  --query connectionString -o tsv 2>/dev/null || echo "")
[[ -z "$APPLICATIONINSIGHTS_CONNECTION_STRING" ]] && \
  echo "##vso[task.logissue type=warning]Application Insights resource not found — telemetry will be disabled"

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
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

# ── Submit all Run Commands, then wait in parallel ─────────────────────────────
# Arrays to track per-machine state
declare -a MACHINE_NAMES=()
declare -a RUN_CMD_NAMES=()

# API_ENVIRONMENT is used to set the AET and port for the MWL and PACS servers.
API_ENVIRONMENT=$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')
if [[ ${#API_ENVIRONMENT} -gt 4 ]]; then
  API_ENVIRONMENT=${API_ENVIRONMENT:0:3} # Truncate REVIEW and PREPROD to 3 chars to fit within AET length limit
fi

while IFS= read -r MACHINE_JSON; do
  MACHINE=$(echo "$MACHINE_JSON" | jq -r '.name')
  LOCATION=$(echo "$MACHINE_JSON" | jq -r '.location')
  echo "Preparing deploy for $MACHINE ($LOCATION)..."

RELAY_AUTH_BLOCK=""
if [[ "${ENV_CONFIG}" == "review" && -n "${AZURE_RELAY_SHARED_ACCESS_KEY:-}" ]]; then
  RELAY_AUTH_BLOCK="AZURE_RELAY_KEY_NAME=listen
AZURE_RELAY_SHARED_ACCESS_KEY=${AZURE_RELAY_SHARED_ACCESS_KEY}
"
fi

  # Build .env, then base64-encode to pass newlines as a run command parameter.
  # NOTE: Arc Run Command drops protectedParameters for inline source.script,
  # so EnvContentB64 travels as a regular parameter (base64-encoded, not plain text).
  ENV_CONTENT="AZURE_RELAY_NAMESPACE=${RELAY_NAMESPACE_HOSTNAME}
  AZURE_RELAY_HYBRID_CONNECTION=hc-${MACHINE}
  CLOUD_API_ENDPOINT=${CLOUD_API_ENDPOINT}
  CLOUD_API_RESOURCE=${CLOUD_API_RESOURCE}
  APPLICATIONINSIGHTS_CONNECTION_STRING=${APPLICATIONINSIGHTS_CONNECTION_STRING}
  ENVIRONMENT=${ENVIRONMENT}
  MWL_AET=RUBIE_MWL_${API_ENVIRONMENT}
  MWL_PORT=104
  MWL_DB_PATH=${BASE_PATH}/data/worklist.db
  PACS_AET=RUBIE_PACS_${API_ENVIRONMENT}
  PACS_PORT=11112
  PACS_STORAGE_PATH=${BASE_PATH}/data/storage
  PACS_DB_PATH=${BASE_PATH}/data/pacs.db
  LOG_LEVEL=INFO
  ${RELAY_AUTH_BLOCK}SAMPLE_IMAGES_PATH=${BASE_PATH}/current/sample_images"

  # Cross-platform base64 encoding (works on macOS and Linux)
  ENV_CONTENT_B64=$(printf '%s' "$ENV_CONTENT" | base64 | tr -d '\n')

  # deploy.ps1 is embedded directly in source.script (limit ~4 MB) rather than passed
  # as a parameter value. Parameter values are passed on the PowerShell command line and
  # the Windows command line limit (32,767 chars) would be exceeded by the ~40 KB script.

  # Use machine name + timestamp to ensure uniqueness across parallel submissions.
  CLEAN_TAG=$(echo "${RELEASE_TAG}" | tr '.' '-' | tr '/' '-')
  RUN_CMD_NAME="deploy-mbsgw-${CLEAN_TAG}-${MACHINE}"

  CMD_URL="https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${ARC_RG}/providers/Microsoft.HybridCompute/machines/${MACHINE}/runCommands/${RUN_CMD_NAME}?api-version=2024-07-10"

  BODY=$(jq -n \
    --arg loc    "$LOCATION" \
    --rawfile script scripts/powershell/deploy.ps1 \
    --arg tag    "$RELEASE_TAG" \
    --arg pyver  "$PYTHON_VERSION" \
    --arg envb64 "$ENV_CONTENT_B64" \
    --arg token  "$GITHUB_TOKEN" \
    --arg env    "$ENVIRONMENT" \
    '{
      location: $loc,
      properties: {
        source: { script: $script },
        parameters: [
          { name: "ReleaseTag",    value: $tag   },
          { name: "PythonVersion", value: $pyver },
          { name: "EnvContentB64", value: $envb64 },
          { name: "GitHubToken",   value: $token },
          { name: "Environment",   value: $env }
        ],
        runAsSystem:      true,
        timeoutInSeconds: 1800
      }
    }')

  echo "Submitting run command '$RUN_CMD_NAME' for $MACHINE..."
  PUT_RESPONSE=$(az rest --method PUT \
    --url "$CMD_URL" \
    --body "$BODY" \
    --output json)

  PROV_STATE=$(echo "$PUT_RESPONSE" | jq -r '.properties.provisioningState // "unknown"')
  echo "Run command submitted for $MACHINE: $PROV_STATE"

  MACHINE_NAMES+=("$MACHINE")
  RUN_CMD_NAMES+=("$RUN_CMD_NAME")

done < <(echo "$MACHINES_JSON" | jq -c '.[]')

# ── Wait for all machines in parallel ─────────────────────────────────────────
echo "Waiting for ${#MACHINE_NAMES[@]} machine(s) in parallel..."

declare -a PIDS=()
for i in "${!MACHINE_NAMES[@]}"; do
  MACHINE="${MACHINE_NAMES[$i]}"
  RUN_CMD_NAME="${RUN_CMD_NAMES[$i]}"
  (
    scripts/bash/wait_arc_run_command.sh "$MACHINE" "$ARC_RG" "$RUN_CMD_NAME" \
      && echo "Deploy succeeded for $MACHINE" \
      || { echo "ERROR: Deploy failed for $MACHINE"; exit 1; }
  ) &
  PIDS+=($!)
done

FAILED=0
for i in "${!PIDS[@]}"; do
  if ! wait "${PIDS[$i]}"; then
    FAILED=1
  fi
done

exit $FAILED
