# Log Analytics Workspace
module "log_analytics_workspace" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/log-analytics-workspace"

  name                = "law-${var.app_short_name}-${var.env_config}-arc-uks"
  location            = var.region
  resource_group_name = azurerm_resource_group.arc_enabled_servers[0].name
  law_sku             = "PerGB2018"
  retention_days      = 30

  monitor_diagnostic_setting_log_analytics_workspace_enabled_logs = ["Audit"]
  monitor_diagnostic_setting_log_analytics_workspace_metrics      = ["AllMetrics"]
}

# Data Collection Rule (DCR)
resource "azurerm_monitor_data_collection_rule" "arc" {
  count = var.enable_arc_servers ? 1 : 0

  name                = "dcr-${var.app_short_name}-${var.env_config}-arc-uks"
  location            = var.region
  resource_group_name = azurerm_resource_group.arc_enabled_servers[0].name

  destinations {
    log_analytics {
      workspace_resource_id = module.log_analytics_workspace[0].id
      name                  = "law-destination"
    }
  }

  data_flow {
    streams      = ["Microsoft-Event", "Microsoft-Perf"]
    destinations = ["law-destination"]
  }

  data_sources {
    windows_event_log {
      name    = "windows-events"
      streams = ["Microsoft-Event"]
      x_path_queries = [
        "System!*[System[(Level=1 or Level=2 or Level=3)]]",
        "Application!*[System[(Level=1 or Level=2 or Level=3)]]",
      ]
    }

    performance_counter {
      name                          = "perf-counters"
      streams                       = ["Microsoft-Perf"]
      sampling_frequency_in_seconds = 60
      counter_specifiers = [
        "\\Processor(_Total)\\% Processor Time",
        "\\Memory\\Available MBytes",
        "\\LogicalDisk(_Total)\\% Free Space",
        "\\LogicalDisk(_Total)\\Disk Reads/sec",
        "\\LogicalDisk(_Total)\\Disk Writes/sec",
        "\\Network Interface(*)\\Bytes Total/sec",
      ]
    }
  }
}

# Managed Identity for policy remediation
module "arc_monitor_policy_identity" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/managed-identity"

  uai_name            = "mi-${var.app_short_name}-${var.env_config}-arc-monitor-uks"
  resource_group_name = azurerm_resource_group.arc_enabled_servers[0].name
  location            = var.region
}

# Grants the identity permission to deploy AMA on Arc-enabled servers
module "arc_monitor_policy_connected_machine_role" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Azure Connected Machine Resource Administrator"
  principal_id         = module.arc_monitor_policy_identity[0].principal_id
}

# Grants the identity permission to create DCR associations and configure workspaces
module "arc_monitor_policy_log_analytics_role" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Log Analytics Contributor"
  principal_id         = module.arc_monitor_policy_identity[0].principal_id
}

# ---------------------------------------------------------------------------
# Policy Assignments for Arc-enabled servers
# AMA install:  "Configure Windows Arc-enabled machines to run Azure Monitor Agent"
# DCR associate: "Configure Windows Arc-enabled machines to be associated with a DCR"
# ---------------------------------------------------------------------------
resource "azurerm_resource_group_policy_assignment" "ama_install" {
  count = var.enable_arc_servers ? 1 : 0

  name                 = "ama-install-arc-${var.env_config}"
  resource_group_id    = azurerm_resource_group.arc_enabled_servers[0].id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/4efbd9d8-6bc6-45f6-9be2-7fe9dd5d89ff"
  location             = var.region

  identity {
    type         = "UserAssigned"
    identity_ids = [module.arc_monitor_policy_identity[0].id]
  }
}

resource "azurerm_resource_group_policy_assignment" "dcr_association" {
  count = var.enable_arc_servers ? 1 : 0

  name                 = "dcr-assoc-arc-${var.env_config}"
  resource_group_id    = azurerm_resource_group.arc_enabled_servers[0].id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/eab1f514-22e3-42e3-9a1f-e1dc9199355c"
  location             = var.region

  identity {
    type         = "UserAssigned"
    identity_ids = [module.arc_monitor_policy_identity[0].id]
  }

  parameters = jsonencode({
    dcrResourceId = { value = azurerm_monitor_data_collection_rule.arc[0].id }
    resourceType  = { value = "Microsoft.Insights/dataCollectionRules" }
  })
}
