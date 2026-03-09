#!/bin/bash
# Poll an Arc Run Command until it completes, printing output on completion.
# Usage: wait_arc_run_command.sh <machine-name> <resource-group> <run-command-name>
#
# provisioningState: Succeeded only means ARM accepted the resource.
# instanceView.executionState carries the actual script execution status.

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

  PROVISIONING_STATE=$(echo "$CMD_JSON" | jq -r '.provisioningState // "Unknown"')
  EXEC_STATE=$(echo "$CMD_JSON"        | jq -r '.instanceView.executionState // "Unknown"')

  CURRENT_TIME=$(date +%s)
  ELAPSED=$((CURRENT_TIME - START_TIME))

  # Terminal conditions:
  # - ARM itself failed/canceled (script will never run)
  # - OR the script execution reached a terminal state
  TERMINAL=false
  if [[ "$PROVISIONING_STATE" == "Failed" || "$PROVISIONING_STATE" == "Canceled" ]]; then
    TERMINAL=true
  elif [[ "$EXEC_STATE" == "Succeeded" || "$EXEC_STATE" == "Failed" \
       || "$EXEC_STATE" == "TimedOut"  || "$EXEC_STATE" == "Canceled" ]]; then
    TERMINAL=true
  fi

  if $TERMINAL; then
    EXIT_CODE=$(echo "$CMD_JSON" | jq -r '.instanceView.exitCode // -1')
    OUTPUT=$(echo "$CMD_JSON"    | jq -r '.instanceView.output // ""')
    ERROR_OUT=$(echo "$CMD_JSON" | jq -r '.instanceView.error // ""')

    [[ -n "$OUTPUT"    ]] && echo "=== Script output ===" && echo "$OUTPUT"
    [[ -n "$ERROR_OUT" ]] && echo "=== Script error ===" && echo "$ERROR_OUT"

    if [[ "$EXEC_STATE" == "Succeeded" && "$EXIT_CODE" == "0" ]]; then
      echo "Arc Run Command '$CMD_NAME' on '$MACHINE' succeeded."
      exit 0
    else
      echo "Arc Run Command '$CMD_NAME' on '$MACHINE' failed: provisioningState=$PROVISIONING_STATE, executionState=$EXEC_STATE, exitCode=$EXIT_CODE"
      echo "=== Full instanceView ==="
      echo "$CMD_JSON" | jq '.instanceView'
      exit 1
    fi
  fi

  if (( ELAPSED > TIMEOUT_SECONDS )); then
    echo "ERROR: Timeout (${TIMEOUT_SECONDS}s) waiting for '$CMD_NAME' on '$MACHINE'"
    echo "=== Full instanceView at timeout ==="
    echo "$CMD_JSON" | jq '.instanceView'
    exit 2
  fi

  echo "State: provisioning=$PROVISIONING_STATE execution=$EXEC_STATE (${ELAPSED}s elapsed)"
  sleep "$SLEEP_TIME"
done
