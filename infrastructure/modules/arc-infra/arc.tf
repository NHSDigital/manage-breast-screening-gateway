# Resource group for Arc-enabled servers — created by resource-group-init (Bicep),
# not managed by Terraform, so it exists before this module runs.
data "azurerm_resource_group" "arc_enabled_servers" {
  count = var.enable_arc_servers ? 1 : 0

  name = "${var.resource_group_name}-arc-enabled-servers"
}

# Look up the Arc onboarding service principal by its standard name
data "azuread_service_principal" "arc_onboarding" {
  count        = var.enable_arc_servers ? 1 : 0
  display_name = "spn-azure-arc-onboarding-screening-${var.env_config}"
}

# Look up the Entra ID group that manages this environment
data "azuread_group" "screening" {
  count        = var.enable_arc_servers ? 1 : 0
  display_name = "screening_${var.app_short_name}_${var.env_config}"
}

# Assign "Azure Connected Machine Onboarding" role to allow Arc server enrollment
module "arc_onboarding_role" {
  count = var.enable_arc_servers ? 1 : 0

  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = data.azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Azure Connected Machine Onboarding"
  principal_id         = data.azuread_service_principal.arc_onboarding[0].object_id
}

# Assign "Windows Admin Center Administrator Login" to allow the group to connect via WAC
module "arc_wac_admin_login_role" {
  count = var.enable_arc_servers ? 1 : 0

  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = data.azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Windows Admin Center Administrator Login"
  principal_id         = data.azuread_group.screening[0].object_id
}
