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
MACHINE_NAMES=()
PIDS=()
MACHINE_INDEX=0

run_smoke_test() {
  local machine="$1"
  local run_name="$2"
  local result=0

  echo "--- Smoke test: ${machine} (run command: ${run_name}) ---"

  ( az connectedmachine run-command create \
    --name "${run_name}" \
    --machine-name "${machine}" \
    --resource-group "${RESOURCE_GROUP}" \
    --location "${LOCATION}" \
    --script "${SCRIPT_CONTENT}" \
    --output none ) &

    echo "--- Waiting for smoke test to complete on ${machine} ---"

    # Poll until the run command completes (max 10 minutes, 10s interval)
    for i in $(seq 1 60); do
      EXEC_STATE=$(az connectedmachine run-command show \
        --name "${run_name}" \
        --machine-name "${machine}" \
        --resource-group "${RESOURCE_GROUP}" \
        --query "instanceView.executionState" \
        --output tsv 2>/dev/null || echo "Unknown")

      if [[ "$EXEC_STATE" == "Succeeded" ]]; then
        echo "✓ ${machine}: smoke test passed"
        break
      elif [[ "$EXEC_STATE" == "Failed" ]]; then
        OUTPUT=$(az connectedmachine run-command show \
          --name "${run_name}" \
          --machine-name "${machine}" \
          --resource-group "${RESOURCE_GROUP}" \
          --query "instanceView.output" \
          --output tsv 2>/dev/null || echo "(no output)")
        ERROR=$(az connectedmachine run-command show \
          --name "${run_name}" \
          --machine-name "${machine}" \
          --resource-group "${RESOURCE_GROUP}" \
          --query "instanceView.error" \
          --output tsv 2>/dev/null || echo "(no error)")
        echo "✗ ${machine}: smoke test FAILED"
        echo "  Output: ${OUTPUT}"
        echo "  Error:  ${ERROR}"
        result=1
        break
      fi

      if [[ $i -eq 60 ]]; then
        echo "✗ ${machine}: timed out after 10 minutes (last state: ${EXEC_STATE})"
        result=1
      else
        echo "  ${machine}: [${i}/60] ${EXEC_STATE} — waiting 10s..."
        sleep 10
      fi
    done

  # Clean up the run command resource regardless of outcome.
  az connectedmachine run-command delete \
    --name "${run_name}" \
    --machine-name "${machine}" \
    --resource-group "${RESOURCE_GROUP}" \
    --yes --output none 2>/dev/null || true

  return "$result"
}

while IFS= read -r MACHINE; do
  [[ -z "$MACHINE" ]] && continue

  MACHINE_NAMES+=("${MACHINE}")
  MACHINE_INDEX=$((MACHINE_INDEX + 1))
  RUN_NAME="smoke-$(date +%s)-${MACHINE_INDEX}"
  echo "Starting smoke test on ${MACHINE} (run command: ${RUN_NAME})..."
  ( run_smoke_test "${MACHINE}" "${RUN_NAME}" ) &
  PIDS+=("$!")

done <<< "$MACHINES"

echo "Started smoke tests on ${#MACHINE_NAMES[@]} machine(s) in parallel."

for i in "${!PIDS[@]}"; do
  echo ""
  if ! wait "${PIDS[$i]}"; then
    FAILED_MACHINES+=("${MACHINE_NAMES[$i]}")
  fi
done

echo ""
if [[ ${#FAILED_MACHINES[@]} -gt 0 ]]; then
  echo "::error::Smoke test failed on: ${FAILED_MACHINES[*]}"
  exit 1
fi

echo "All smoke tests passed for ${ENVIRONMENT}"
