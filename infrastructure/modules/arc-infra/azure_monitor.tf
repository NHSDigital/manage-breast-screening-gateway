# Log Analytics Workspace
module "log_analytics_workspace" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/log-analytics-workspace"

  name                = "law-${var.app_short_name}-${var.env_config}-arc-uks"
  location            = var.region
  resource_group_name = data.azurerm_resource_group.arc_enabled_servers[0].name
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
  resource_group_name = data.azurerm_resource_group.arc_enabled_servers[0].name

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
  resource_group_name = data.azurerm_resource_group.arc_enabled_servers[0].name
  location            = var.region
}

# Grants the identity permission to deploy AMA on Arc-enabled servers
module "arc_monitor_policy_connected_machine_role" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = data.azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Azure Connected Machine Resource Administrator"
  principal_id         = module.arc_monitor_policy_identity[0].principal_id
}

# Grants the identity permission to configure Log Analytics workspaces
module "arc_monitor_policy_log_analytics_role" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = data.azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Log Analytics Contributor"
  principal_id         = module.arc_monitor_policy_identity[0].principal_id
}

# Grants the identity permission to write DCR associations on Arc machine resources
module "arc_monitor_policy_monitoring_contributor_role" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = data.azurerm_resource_group.arc_enabled_servers[0].id
  role_definition_name = "Monitoring Contributor"
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
  resource_group_id    = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/94f686d6-9a24-4e19-91f1-de937dc171a4"
  location             = var.region

  identity {
    type         = "UserAssigned"
    identity_ids = [module.arc_monitor_policy_identity[0].id]
  }
}

resource "azurerm_resource_group_policy_assignment" "dcr_association" {
  count = var.enable_arc_servers ? 1 : 0

  name                 = "dcr-assoc-arc-${var.env_config}"
  resource_group_id    = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_definition_id = "/providers/Microsoft.Authorization/policyDefinitions/c24c537f-2516-4c2f-aac5-2cd26baa3d26"
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

# ---------------------------------------------------------------------------
# Custom Policy Definition + Assignment for Windows Admin Center
# Replicates the built-in "Configure Windows Arc-enabled machines to enable
# Windows Admin Center Extension" (0e4b8929), which is not available in this tenant.
# Policy rule is defined in policies/deploy-wac-extension-arc-windows.json.
# ---------------------------------------------------------------------------
resource "azurerm_policy_definition" "wac" {
  count = var.enable_arc_servers ? 1 : 0

  name         = "deploy-wac-extension-arc-windows-${var.env_config}"
  policy_type  = "Custom"
  mode         = "Indexed"
  display_name = "Configure Windows Arc-enabled machines to enable Windows Admin Center Extension"
  description  = "Deploys the AdminCenter extension to Windows Arc-enabled machines to enable browser-based management via the Azure portal."

  parameters = jsonencode({
    effect = {
      type          = "String"
      metadata      = { displayName = "Effect", description = "Enable or disable the execution of the policy" }
      allowedValues = ["DeployIfNotExists", "Disabled"]
      defaultValue  = "DeployIfNotExists"
    }
    port = {
      type         = "Integer"
      metadata     = { displayName = "Port", description = "The port number to use for Windows Admin Center" }
      defaultValue = 6516
    }
    proxyURL = {
      type         = "String"
      metadata     = { displayName = "Proxy URL", description = "Optional proxy URL for Windows Admin Center" }
      defaultValue = ""
    }
  })

  policy_rule = file("${path.module}/policies/deploy-wac-extension-arc-windows.json")
}

resource "azurerm_resource_group_policy_assignment" "wac" {
  count = var.enable_arc_servers ? 1 : 0

  name                 = "wac-arc-${var.env_config}"
  resource_group_id    = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_definition_id = azurerm_policy_definition.wac[0].id
  location             = var.region

  identity {
    type         = "UserAssigned"
    identity_ids = [module.arc_monitor_policy_identity[0].id]
  }
}

# Remediation tasks — re-evaluate compliance and deploy AMA/DCR association on
# any non-compliant Arc machines each time Terraform applies. Combined with the
# DeployIfNotExists effect, this makes the monitoring setup self-healing.
resource "azurerm_resource_group_policy_remediation" "ama_install" {
  count = var.enable_arc_servers ? 1 : 0

  name                    = "remediation-ama-install-${var.env_config}"
  resource_group_id       = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_assignment_id    = azurerm_resource_group_policy_assignment.ama_install[0].id
  resource_discovery_mode = "ReEvaluateCompliance"
}

resource "azurerm_resource_group_policy_remediation" "dcr_association" {
  count = var.enable_arc_servers ? 1 : 0

  name                    = "remediation-dcr-assoc-${var.env_config}"
  resource_group_id       = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_assignment_id    = azurerm_resource_group_policy_assignment.dcr_association[0].id
  resource_discovery_mode = "ReEvaluateCompliance"
}

resource "azurerm_resource_group_policy_remediation" "wac" {
  count = var.enable_arc_servers ? 1 : 0

  name                    = "remediation-wac-${var.env_config}"
  resource_group_id       = data.azurerm_resource_group.arc_enabled_servers[0].id
  policy_assignment_id    = azurerm_resource_group_policy_assignment.wac[0].id
  resource_discovery_mode = "ReEvaluateCompliance"
}

module "app_insights" {
  count  = var.enable_arc_servers ? 1 : 0
  source = "../dtos-devops-templates/infrastructure/modules/app-insights"

  name                       = "ai-${var.app_short_name}-${var.env_config}-arc-uks"
  location                   = var.region
  resource_group_name        = data.azurerm_resource_group.arc_enabled_servers[0].name
  appinsights_type           = "other"
  log_analytics_workspace_id = module.log_analytics_workspace[0].id
}
