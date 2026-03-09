#!/bin/bash
# Poll an Arc Run Command until it completes, printing output on completion.
# Usage: wait_arc_run_command.sh <machine-name> <resource-group> <run-command-name>

set -euo pipefail

MACHINE=$1
RG=$2
CMD_NAME=$3

SLEEP_TIME=20
TIMEOUT_SECONDS=1800

echo "Waiting for Arc Run Command '$CMD_NAME' on '$MACHINE'..."

START_TIME=$(date +%s)

while true; do
  CMD_JSON=$(az connectedmachine run-command show \
    --resource-group "$RG" \
    --machine-name "$MACHINE" \
    --run-command-name "$CMD_NAME" \
    --output json 2>/dev/null)

  STATE=$(echo "$CMD_JSON" | jq -r '.provisioningState // "Unknown"')

  if [[ "$STATE" != "Creating" && "$STATE" != "Updating" ]]; then
    EXIT_CODE=$(echo "$CMD_JSON" | jq -r '.instanceView.exitCode // -1')
    OUTPUT=$(echo "$CMD_JSON" | jq -r '.instanceView.output // ""')
    ERROR_OUT=$(echo "$CMD_JSON" | jq -r '.instanceView.error // ""')

    [[ -n "$OUTPUT" ]] && echo "=== Script output ===" && echo "$OUTPUT"
    [[ -n "$ERROR_OUT" ]] && echo "=== Script error ===" && echo "$ERROR_OUT"

    if [[ "$STATE" == "Succeeded" && "$EXIT_CODE" == "0" ]]; then
      echo "Arc Run Command '$CMD_NAME' on '$MACHINE' succeeded."
      exit 0
    else
      echo "Arc Run Command '$CMD_NAME' on '$MACHINE' failed: state=$STATE, exitCode=$EXIT_CODE"
      exit 1
    fi
  fi

  CURRENT_TIME=$(date +%s)
  ELAPSED=$((CURRENT_TIME - START_TIME))
  if (( ELAPSED > TIMEOUT_SECONDS )); then
    echo "ERROR: Timeout (${TIMEOUT_SECONDS}s) waiting for '$CMD_NAME' on '$MACHINE'"
    exit 2
  fi

  echo "State: $STATE (${ELAPSED}s elapsed)"
  sleep "$SLEEP_TIME"
done
