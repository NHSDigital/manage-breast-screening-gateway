# Resource group for all gateway test VM infrastructure
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.region
}

# Look up the environment Entra ID group for VM login access
data "azuread_group" "vm_login" {
  display_name = "screening_mbsgw_${var.env_config}"
}

# Grant Virtual Machine Administrator Login to the Entra ID group on the resource group.
# Required for Bastion to offer the Microsoft Entra ID authentication option.
module "vm_login_role" {
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = azurerm_resource_group.main.id
  role_definition_name = "Virtual Machine Administrator Login"
  principal_id         = data.azuread_group.vm_login.object_id
}

# Log Analytics workspace for monitoring VNet, Bastion, and the test VM
module "log_analytics_workspace" {
  source = "../dtos-devops-templates/infrastructure/modules/log-analytics-workspace"

  name                = "log-${var.app_short_name}-${var.env_config}-uks"
  location            = var.region
  resource_group_name = azurerm_resource_group.main.name
  law_sku             = "PerGB2018"
  retention_days      = 30

  monitor_diagnostic_setting_log_analytics_workspace_enabled_logs = []
  monitor_diagnostic_setting_log_analytics_workspace_metrics      = ["AllMetrics"]
}
