extension microsoftGraphV1

param enterpriseAppClientId string
param enterpriseAppName string
param groupMemberIds array = []

resource enterpriseAppSp 'Microsoft.Graph/servicePrincipals@v1.0' = {
  appId: enterpriseAppClientId
  owners: {
    relationships: groupMemberIds
  }
}

resource enterpriseApp 'Microsoft.Graph/applications@v1.0' = {
  uniqueName: enterpriseAppName
  displayName: enterpriseAppName
  owners: {
    relationships: groupMemberIds
  }
}
