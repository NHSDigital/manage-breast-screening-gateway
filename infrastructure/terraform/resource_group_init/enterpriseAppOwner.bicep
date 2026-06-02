extension microsoftGraphV1

param miPrincipalId string
param enterpriseAppClientId string
param enterpriseAppName string
param groupMemberIds array = []

resource enterpriseAppSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: enterpriseAppClientId
  owners: {
    relationships: concat([miPrincipalId], groupMemberIds)
  }
}

resource enterpriseApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: enterpriseAppName
  displayName: enterpriseAppName
  owners: {
    relationships: groupMemberIds
  }
}
