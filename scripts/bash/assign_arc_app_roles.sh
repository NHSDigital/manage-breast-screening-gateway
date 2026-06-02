#!/usr/bin/env bash
set -eu

ENV_CONFIG="$1"

enterpriseAppName="spn-manbrs-web-api-${ENV_CONFIG}"
rgName="rg-mbsgw-${ENV_CONFIG}-uks-arc-enabled-servers"
appRoleValue="Gateway.Access"

echo "Fetching enterprise app details for: $enterpriseAppName"
spObjectId=$(az ad sp list --filter "displayName eq '${enterpriseAppName}'" --query "[0].id" -o tsv)
appRoleId=$(az ad sp list --filter "displayName eq '${enterpriseAppName}'" --query "[0].appRoles[?value=='${appRoleValue}'].id | [0]" -o tsv)

if [ -z "$spObjectId" ]; then
  echo "Error: Enterprise app '$enterpriseAppName' not found"
  exit 1
fi

echo "SP object ID:          $spObjectId"
echo "App role ($appRoleValue): $appRoleId"

echo "Listing Arc machines in: $rgName"
arcMachines=$(az connectedmachine list --resource-group "$rgName" --query "[].name" -o tsv)

if [ -z "$arcMachines" ]; then
  echo "No Arc machines found in $rgName"
  exit 0
fi

while IFS= read -r machine; do
  [ -z "$machine" ] && continue

  miPrincipalId=$(az connectedmachine show \
    --resource-group "$rgName" \
    --name "$machine" \
    --query "identity.principalId" -o tsv)

  echo "Assigning $appRoleValue to $machine (MI: $miPrincipalId)..."
  if ! output=$(az rest --method POST \
    --uri "https://graph.microsoft.com/v1.0/servicePrincipals/${spObjectId}/appRoleAssignedTo" \
    --headers "Content-Type=application/json" \
    --body "{\"principalId\": \"${miPrincipalId}\", \"resourceId\": \"${spObjectId}\", \"appRoleId\": \"${appRoleId}\"}" 2>&1); then
    if echo "$output" | grep -q "Permission being assigned already exists"; then
      echo "  Already assigned, skipping."
    else
      echo "Error: $output"
      exit 1
    fi
  fi
done <<< "$arcMachines"

echo "Done."
