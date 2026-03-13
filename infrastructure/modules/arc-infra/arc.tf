# Resource group for Arc-enabled servers (where machines register on onboarding)
resource "azurerm_resource_group" "arc_enabled_servers" {
  count = var.enable_arc_servers ? 1 : 0

  name     = "${var.resource_group_name}-arc-enabled-servers"
  location = var.region
}

# Look up the Arc onboarding service principal by its standard name
data "azuread_service_principal" "arc_onboarding" {
  count        = var.enable_arc_servers ? 1 : 0
  display_name = "spn-azure-arc-onboarding-screening-${var.env_config}"
}

# Assign "Azure Connected Machine Onboarding" role to allow Arc server enrollment
module "arc_onboarding_role" {
  count = var.enable_arc_servers ? 1 : 0

  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Azure Connected Machine Onboarding"
  principal_id         = data.azuread_service_principal.arc_onboarding[0].object_id
}
