#!/usr/bin/env bash
set -eu

REGION="$1"
HUB_SUBSCRIPTION_ID="$2"
ENABLE_SOFT_DELETE="$3"
ENV_CONFIG="$4"
STORAGE_ACCOUNT_RG="$5"
STORAGE_ACCOUNT_NAME="$6"
APP_SHORT_NAME="$7"
ARM_SUBSCRIPTION_ID="$8"

# Dynamic Group Lookup
userGroupName="screening_${APP_SHORT_NAME}_${ENV_CONFIG}"
echo "Fetching object id for group: $userGroupName"
userGroupPrincipalID=$(az ad group show --group "$userGroupName" --query id -o tsv)

if [ -z "$userGroupPrincipalID" ]; then
  echo "Error: Group '$userGroupName' not found in Entra ID"
  exit 1
fi

echo "Found group Object ID: $userGroupPrincipalID"

echo "Fetching members of group: $userGroupName"
groupMemberIds=$(az ad group member list --group "$userGroupName" --query "[].id" -o json)
echo "Found group members: $groupMemberIds"

enterpriseAppName="spn-manbrs-web-api-${ENV_CONFIG}"
echo "Fetching appId for enterprise app: $enterpriseAppName"
enterpriseAppClientId=$(az ad sp list --filter "displayName eq '${enterpriseAppName}'" --query "[0].appId" -o tsv)

if [ -z "$enterpriseAppClientId" ]; then
  echo "Error: Enterprise app '$enterpriseAppName' not found in Entra ID"
  exit 1
fi

echo "Found enterprise app client ID: $enterpriseAppClientId"

echo "Checking uniqueName on application registration $enterpriseAppName..."
appObjectId=$(az ad app show --id "$enterpriseAppClientId" --query id -o tsv)
currentUniqueName=$(az rest --method GET \
  --uri "https://graph.microsoft.com/v1.0/applications/${appObjectId}?\$select=uniqueName" \
  --query uniqueName -o tsv 2>/dev/null || echo "")
if [ -z "$currentUniqueName" ]; then
  echo "Setting uniqueName to: $enterpriseAppName"
  az rest --method PATCH \
    --uri "https://graph.microsoft.com/v1.0/applications/${appObjectId}" \
    --headers "Content-Type=application/json" \
    --body "{\"uniqueName\": \"${enterpriseAppName}\"}"
else
  echo "uniqueName already set to: $currentUniqueName"
fi

echo "Deploy to hub subscription $HUB_SUBSCRIPTION_ID..."
az deployment sub create --location "$REGION" --template-file infrastructure/terraform/resource_group_init/main.bicep \
  --subscription "$HUB_SUBSCRIPTION_ID" \
  --parameters enableSoftDelete="$ENABLE_SOFT_DELETE" envConfig="$ENV_CONFIG" region="$REGION" \
    storageAccountRGName="$STORAGE_ACCOUNT_RG" storageAccountName="$STORAGE_ACCOUNT_NAME" \
    appShortName="$APP_SHORT_NAME" userGroupPrincipalID="$userGroupPrincipalID" \
    enterpriseAppClientId="$enterpriseAppClientId" groupMemberIds="$groupMemberIds" --what-if

read -r -p "Are you sure you want to execute the deployment? (y/n): " confirm
[[ "$confirm" != "y" ]] && exit 0

output=$(az deployment sub create --location "$REGION" --template-file infrastructure/terraform/resource_group_init/main.bicep \
  --subscription "$HUB_SUBSCRIPTION_ID" \
  --parameters enableSoftDelete="$ENABLE_SOFT_DELETE" envConfig="$ENV_CONFIG" region="$REGION" \
    storageAccountRGName="$STORAGE_ACCOUNT_RG" storageAccountName="$STORAGE_ACCOUNT_NAME" \
    appShortName="$APP_SHORT_NAME" userGroupPrincipalID="$userGroupPrincipalID" \
    enterpriseAppClientId="$enterpriseAppClientId" groupMemberIds="$groupMemberIds")

echo "$output"

echo Capture the outputs...
miName=$(echo "$output" | jq -r '.properties.outputs.miName.value')
miPrincipalID=$(echo "$output" | jq -r '.properties.outputs.miPrincipalID.value')

echo "Deploy to core subscription $ARM_SUBSCRIPTION_ID..."
az deployment sub create --location "$REGION" --template-file infrastructure/terraform/resource_group_init/core.bicep \
  --subscription "$ARM_SUBSCRIPTION_ID" \
  --parameters miName="$miName" miPrincipalId="$miPrincipalID" \
    userGroupPrincipalID="$userGroupPrincipalID" userGroupName="$userGroupName" \
    appShortName="$APP_SHORT_NAME" envConfig="$ENV_CONFIG" region="$REGION" --confirm-with-what-if
