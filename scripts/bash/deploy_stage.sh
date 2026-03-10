#!/bin/bash
# Deploy the gateway app to each ring in sequence.
# A ring with no machines is skipped gracefully.
# Any machine failure fails the ring and stops further rings.
#
# Usage: deploy_stage.sh <environment> "<space-separated rings>" <release_tag>
# Env:   ARM_TENANT_ID, ARM_CLIENT_ID, ARM_OIDC_TOKEN, ARM_USE_OIDC (set by AzureCLI@2 task)

set -euo pipefail

ENVIRONMENT=$1
RINGS=$2
RELEASE_TAG=$3

APP_SHORT_NAME="mbsgw"
KV_NAME="kv-${APP_SHORT_NAME}-${ENVIRONMENT}-inf"

echo "========================================"
echo "Environment : ${ENVIRONMENT}"
echo "Rings       : ${RINGS}"
echo "Release     : ${RELEASE_TAG}"
echo "========================================"

for RING in $RINGS; do
  scripts/bash/deploy_arc_ring.sh "$ENVIRONMENT" "$RING" "$RELEASE_TAG" "$KV_NAME"
done
