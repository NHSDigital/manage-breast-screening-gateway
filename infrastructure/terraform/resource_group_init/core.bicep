targetScope='subscription'

@minLength(1)
param miPrincipalId string
@minLength(1)
param miName string
@minLength(1)
param userGroupPrincipalID string
@minLength(1)
param userGroupName string
@minLength(1)
param appShortName string
@minLength(1)
param envConfig string
@minLength(1)
param region string

// Arc-enabled servers RG must exist before Terraform runs so the arc-infra module
// can reference it as a data source rather than managing its lifecycle.
resource arcEnabledServersRG 'Microsoft.Resources/resourceGroups@2024-11-01' = {
  name: 'rg-${appShortName}-${envConfig}-uks-arc-enabled-servers'
  location: region
}

// See: https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles
var roleID = {
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  kvSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6' // gitleaks:allow
  kvSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7' // gitleaks:allow
  rbacAdmin: 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  AzureConnectedMachineOnboarding: 'b64e21ea-ac4e-4cdf-9dc9-5b892992bee7'
  AzureConnectedMachineResourceAdministrator: 'cd570a14-e51a-42ad-bac8-bafd67325302'
  logAnalyticsContributor: '92aaf0da-9dab-42b6-94a3-d43ce8d16293'
  resourcePolicyContributor: '36243c78-bf99-498c-9df9-86d9f8d28608'
  virtualMachineAdministratorLogin: '1c0163c0-47e6-4577-8991-ea5c82e286e4'
  windowsAdminCenterAdministratorLogin: 'a6333a3e-0164-44c3-b281-7a577aff287f'
  azureRelayListener: '26e0b698-aa6d-4085-9386-aadae190014d'
}

// Define role assignments for managed identity
var miRoleAssignments = [
  {
    roleName: 'contributor'
    roleId: roleID.contributor
    description: 'Contributor access to subscription'
  }
  {
    roleName: 'kvSecretsUser'
    roleId: roleID.kvSecretsUser
    description: 'kvSecretsUser access to subscription'
  }
  {
    roleName: 'resourcePolicyContributor'
    roleId: roleID.resourcePolicyContributor
    description: 'Resource Policy Contributor — required to create policy assignments for Azure Monitor'
  }
  {
    roleName: 'rbacAdmin'
    roleId: roleID.rbacAdmin
    description: 'RBAC Administrator. Restricted to only assign/remove: Storage Blob Data Contributor, Storage Queue Data Contributor, Azure Connected Machine Onboarding, Azure Connected Machine Resource Administrator, Log Analytics Contributor, Virtual Machine Administrator Login, and Windows Admin Center Administrator Login.'
    // Delegated RBAC: This condition restricts the RBAC Administrator to only manage specific roles.
    // This is a security best practice that prevents the identity from granting itself or others sensitive roles like 'Owner' or 'User Access Administrator'.
    condition: '((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/write\'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${roleID.storageBlobDataContributor}, ${roleID.storageQueueDataContributor}, ${roleID.AzureConnectedMachineOnboarding}, ${roleID.AzureConnectedMachineResourceAdministrator}, ${roleID.logAnalyticsContributor}, ${roleID.virtualMachineAdministratorLogin}, ${roleID.windowsAdminCenterAdministratorLogin}, ${roleID.azureRelayListener}})) AND ((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/delete\'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${roleID.storageBlobDataContributor}, ${roleID.storageQueueDataContributor}, ${roleID.AzureConnectedMachineOnboarding}, ${roleID.AzureConnectedMachineResourceAdministrator}, ${roleID.logAnalyticsContributor}, ${roleID.virtualMachineAdministratorLogin}, ${roleID.windowsAdminCenterAdministratorLogin}, ${roleID.azureRelayListener}}))'
    conditionVersion: '2.0'
  }
]

// Define role assignments for Entra ID group
var groupRoleAssignments = [
  {
    roleName: 'contributor'
    roleId: roleID.contributor
    description: 'Contributor access to subscription'
  }
  {
    roleName: 'kvSecretsOfficer'
    roleId: roleID.kvSecretsOfficer
    description: 'kvSecretsOfficer access to subscription'
  }
  {
    roleName: 'rbacAdmin'
    roleId: roleID.rbacAdmin
    description: 'RBAC Administrator. Restricted to only assign/remove: Storage Blob Data Contributor, Storage Queue Data Contributor, Azure Connected Machine Onboarding, Azure Connected Machine Resource Administrator, Log Analytics Contributor, Virtual Machine Administrator Login, and Windows Admin Center Administrator Login.'
    // Delegated RBAC: This condition restricts the RBAC Administrator to only manage specific roles.
    // This is a security best practice that prevents the identity from granting itself or others sensitive roles like 'Owner' or 'User Access Administrator'.
    condition: '((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/write\'})) OR (@Request[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${roleID.storageBlobDataContributor}, ${roleID.storageQueueDataContributor}, ${roleID.AzureConnectedMachineOnboarding}, ${roleID.AzureConnectedMachineResourceAdministrator}, ${roleID.logAnalyticsContributor}, ${roleID.virtualMachineAdministratorLogin}, ${roleID.windowsAdminCenterAdministratorLogin}, ${roleID.azureRelayListener}})) AND ((!(ActionMatches{\'Microsoft.Authorization/roleAssignments/delete\'})) OR (@Resource[Microsoft.Authorization/roleAssignments:RoleDefinitionId] ForAnyOfAnyValues:GuidEquals {${roleID.storageBlobDataContributor}, ${roleID.storageQueueDataContributor}, ${roleID.AzureConnectedMachineOnboarding}, ${roleID.AzureConnectedMachineResourceAdministrator}, ${roleID.logAnalyticsContributor}, ${roleID.virtualMachineAdministratorLogin}, ${roleID.windowsAdminCenterAdministratorLogin}, ${roleID.azureRelayListener}}))'
    conditionVersion: '2.0'
  }
]

// This creates one resource for each item in the miRoleAssignments array
resource miRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in miRoleAssignments: {
  // guid() ensures unique names for each assignment
  name: guid(subscription().subscriptionId, miPrincipalId, role.roleName)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.roleId)
    principalId: miPrincipalId
    principalType: 'ServicePrincipal'
    description: '${miName} ${role.description}'
    // Conditionally include the 'condition' property only if it exists in the role object
    condition: role.?condition
    conditionVersion: role.?conditionVersion
  }
}]


// This creates one resource for each item in the groupRoleAssignments array
resource groupRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for role in groupRoleAssignments: {
  name: guid(subscription().subscriptionId, userGroupPrincipalID, role.roleName)
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', role.roleId)
    principalId: userGroupPrincipalID
    principalType: 'Group'
    description: '${userGroupName} ${role.description}'
    condition: role.?condition
    conditionVersion: role.?conditionVersion
  }
}]
