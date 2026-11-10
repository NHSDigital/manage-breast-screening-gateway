#!/usr/bin/env bash
# Run a smoke test on all Arc-enabled gateway VMs in the target environment.
#
# Uses az connectedmachine run-command to execute scripts/powershell/smoke_test.ps1
# on each VM via the Azure management plane. No direct network access to hospital
# machines is required — the Arc agent handles the connection.
#
# Usage: bash scripts/bash/smoke_test.sh <environment>
#   environment: dev | preprod | prod
#
# Prerequisites:
#   - Azure login (az login or OIDC via GitHub Actions)
#   - connectedmachine CLI extension (installed automatically if missing)

set -euo pipefail

ENVIRONMENT="${1:?Usage: smoke_test.sh <environment>}"

# shellcheck source=/dev/null
source "infrastructure/environments/${ENVIRONMENT}/variables.sh"

RESOURCE_GROUP="rg-mbsgw-${ENVIRONMENT}-uks-arc-enabled-servers"
LOCATION="uksouth"
SCRIPT_CONTENT=$(cat scripts/powershell/smoke_test.ps1)

echo "Installing connectedmachine CLI extension..."
az extension add --name connectedmachine --yes --output none 2>/dev/null || true

echo "Listing Arc machines in ${RESOURCE_GROUP}..."
MACHINES=$(az connectedmachine list \
  --resource-group "${RESOURCE_GROUP}" \
  --query "[].name" \
  --output tsv 2>/dev/null || echo "")

if [[ -z "$MACHINES" ]]; then
  echo "No Arc machines found in ${RESOURCE_GROUP} — skipping smoke test"
  exit 0
fi

FAILED_MACHINES=()

while IFS= read -r MACHINE; do
  [[ -z "$MACHINE" ]] && continue

  RUN_NAME="smoke-$(date +%s)"
  echo ""
  echo "--- Smoke test: ${MACHINE} (run command: ${RUN_NAME}) ---"

  az connectedmachine run-command create \
    --name "${RUN_NAME}" \
    --machine-name "${MACHINE}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --script "${SCRIPT_CONTENT}" \
    --output none

  echo "--- Waiting for smoke test to complete on ${MACHINE} ---"

  # Poll until the run command completes (max 5 minutes, 10s interval)
  PASSED=false
  for i in $(seq 1 30); do
    EXEC_STATE=$(az connectedmachine run-command show \
      --name "${RUN_NAME}" \
      --machine-name "${MACHINE}" \
      --resource-group "${RESOURCE_GROUP}" \
      --instance-view \
      --query "instanceView.executionState" \
      --output tsv 2>/dev/null || echo "Unknown")

    if [[ "$EXEC_STATE" == "Succeeded" ]]; then
      echo "✓ ${MACHINE}: smoke test passed"
      PASSED=true
      break
    elif [[ "$EXEC_STATE" == "Failed" ]]; then
      OUTPUT=$(az connectedmachine run-command show \
        --name "${RUN_NAME}" \
        --machine-name "${MACHINE}" \
        --resource-group "${RESOURCE_GROUP}" \
        --instance-view \
        --query "instanceView.output" \
        --output tsv 2>/dev/null || echo "(no output)")
      ERROR=$(az connectedmachine run-command show \
        --name "${RUN_NAME}" \
        --machine-name "${MACHINE}" \
        --resource-group "${RESOURCE_GROUP}" \
        --instance-view \
        --query "instanceView.error" \
        --output tsv 2>/dev/null || echo "(no error)")
      echo "✗ ${MACHINE}: smoke test FAILED"
      echo "  Output: ${OUTPUT}"
      echo "  Error:  ${ERROR}"
      break
    fi

    if [[ $i -eq 30 ]]; then
      echo "✗ ${MACHINE}: timed out after 5 minutes (last state: ${EXEC_STATE})"
    else
      echo "  [${i}/30] ${EXEC_STATE} — waiting 10s..."
      sleep 10
    fi
  done

  # Clean up the run command resource regardless of outcome
  az connectedmachine run-command delete \
    --name "${RUN_NAME}" \
    --machine-name "${MACHINE}" \
    --resource-group "${RESOURCE_GROUP}" \
    --yes --output none 2>/dev/null || true

  if [[ "$PASSED" != "true" ]]; then
    FAILED_MACHINES+=("${MACHINE}")
  fi

done <<< "$MACHINES"

echo ""
if [[ ${#FAILED_MACHINES[@]} -gt 0 ]]; then
  echo "::error::Smoke test failed on: ${FAILED_MACHINES[*]}"
  exit 1
fi

echo "All smoke tests passed for ${ENVIRONMENT}"
