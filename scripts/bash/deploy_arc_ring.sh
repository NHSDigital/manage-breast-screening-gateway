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

# Ensure the relay extension is installed
if ! az relay --help &>/dev/null; then
  echo "Installing Azure CLI 'relay' extension..."
  az extension add --name relay || {
    echo "ERROR: Failed to install 'relay' extension. Please run 'az extension add --name relay' manually."
    exit 1
  }
fi

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
GITHUB_TOKEN="${GITHUB_TOKEN:-}"

# ── Submit all Run Commands, then wait in parallel ─────────────────────────────
# Arrays to track per-machine state
declare -a MACHINE_NAMES=()
declare -a RUN_CMD_NAMES=()

while IFS= read -r MACHINE_JSON; do
  MACHINE=$(echo "$MACHINE_JSON" | jq -r '.name')
  LOCATION=$(echo "$MACHINE_JSON" | jq -r '.location')
  echo "Preparing deploy for $MACHINE ($LOCATION)..."

  # Fetch relay SAS key directly — Contributor includes listKeys on relay HCs,
  # and this avoids any dependency on Terraform state having the resource imported.
  echo "Fetching SAS key for hc-${MACHINE} in $RELAY_NAMESPACE_NAME..."
  SAS_KEY=$(az relay hyco authorization-rule keys list \
    --resource-group "$RELAY_RG" \
    --namespace-name "$RELAY_NAMESPACE_NAME" \
    --hybrid-connection-name "hc-${MACHINE}" \
    --name listen \
    --query primaryKey -o tsv 2>/tmp/relay_key_err_${MACHINE}) || {
      ERR=$(cat /tmp/relay_key_err_${MACHINE})
      echo "##vso[task.logissue type=warning]Failed to fetch relay SAS key for hc-${MACHINE}: $ERR"
      SAS_KEY=""
    }

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

API_ENVIRONMENT=$(echo "$ENVIRONMENT" | tr '[:lower:]' '[:upper:]')

if [[ "$ENVIRONMENT" == "preprod" ]]; then
    API_ENVIRONMENT="PRE"
fi
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
MWL_AET=RUBIE_MWL_${API_ENVIRONMENT}
MWL_PORT=104
MWL_DB_PATH=${BASE_PATH}/data/worklist.db
PACS_AET=RUBIE_PACS_${API_ENVIRONMENT}
PACS_PORT=11112
PACS_STORAGE_PATH=${BASE_PATH}/data/storage
PACS_DB_PATH=${BASE_PATH}/data/pacs.db
LOG_LEVEL=INFO"

  # Cross-platform base64 encoding (works on macOS and Linux)
  ENV_CONTENT_B64=$(printf '%s' "$ENV_CONTENT" | base64 | tr -d '\n')

  # deploy.ps1 is embedded directly in source.script (limit ~4 MB) rather than passed
  # as a parameter value. Parameter values are passed on the PowerShell command line and
  # the Windows command line limit (32,767 chars) would be exceeded by the ~40 KB script.

  # Use machine name + timestamp to ensure uniqueness across parallel submissions.
  CLEAN_TAG=$(echo "${RELEASE_TAG}" | tr '.' '-' | tr '/' '-')
  DEPLOY_ID=$(date +%s)
  RUN_CMD_NAME="deploy-mbsgw-${CLEAN_TAG}-${MACHINE}-${DEPLOY_ID}"

  CMD_URL="https://management.azure.com/subscriptions/${SUB_ID}/resourceGroups/${ARC_RG}/providers/Microsoft.HybridCompute/machines/${MACHINE}/runCommands/${RUN_CMD_NAME}?api-version=2024-07-10"

  BODY=$(jq -n \
    --arg loc    "$LOCATION" \
    --rawfile script scripts/powershell/deploy.ps1 \
    --arg tag    "$RELEASE_TAG" \
    --arg pyver  "$PYTHON_VERSION" \
    --arg envb64 "$ENV_CONTENT_B64" \
    --arg token  "$GITHUB_TOKEN" \
    '{
      location: $loc,
      properties: {
        source: { script: $script },
        parameters: [
          { name: "ReleaseTag",    value: $tag   },
          { name: "PythonVersion", value: $pyver },
          { name: "EnvContentB64", value: $envb64 },
          { name: "GitHubToken",   value: $token }
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
