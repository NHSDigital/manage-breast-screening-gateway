# The relay namespace is owned by dtos-manage-breast-screening ("manbrs").
# This module creates one Hybrid Connection + listen-only auth rule per Arc-enabled
# machine, auto-discovered by querying the Arc resource group.
# HC names are derived from the Arc resource name set at onboarding
# (e.g. hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01).
#
# Trigger: run `terraform apply` after each Arc onboarding to pick up new machines.

locals {
  relay_namespace_rg   = "rg-manbrs-${var.env_config}-uks"
  relay_namespace_name = "relay-manbrs-${var.env_config}"
}

# Discover all Arc-enabled machines registered in the Arc resource group.
# Each machine's Arc resource name is set during onboarding
# (e.g. gw-hull-university-teaching-hospitals-nhs-trust-rwa-01).
data "azurerm_resources" "arc_machines" {
  count = var.enable_arc_servers ? 1 : 0

  resource_group_name = data.azurerm_resource_group.arc_enabled_servers[0].name
  type                = "Microsoft.HybridCompute/machines"
}

locals {
  arc_machines_discovered = var.enable_arc_servers ? {
    for m in data.azurerm_resources.arc_machines[0].resources : m.name => m
  } : {}

  # Static machines (e.g. test VM) whose Arc registration happens in the same
  # Terraform run — the data source won't see them yet, so we add them explicitly.
  arc_machines_static = {
    for name in var.static_arc_machine_names : name => { name = name }
  }

  arc_machines = merge(local.arc_machines_discovered, local.arc_machines_static)
}

# One Hybrid Connection per Arc machine (e.g. hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01).
resource "azurerm_relay_hybrid_connection" "per_machine" {
  for_each = local.arc_machines

  name                          = "hc-${each.key}"
  resource_group_name           = local.relay_namespace_rg
  relay_namespace_name          = local.relay_namespace_name
  requires_client_authorization = true
}

# Listen-only SAS rule per HC — retained for local development / break-glass access.
# Production relay authentication uses Managed Identity (see relay_listener_role below).
resource "azurerm_relay_hybrid_connection_authorization_rule" "per_machine_listen" {
  for_each = {
    for machine_name, machine_config in local.arc_machines :
    machine_name => machine_config
    if var.env_config == "review"
  }

  name                   = "listen"
  hybrid_connection_name = azurerm_relay_hybrid_connection.per_machine[each.key].name
  namespace_name         = local.relay_namespace_name
  resource_group_name    = local.relay_namespace_rg

  listen = true
  send   = false
  manage = false
}

# Look up each discovered Arc machine to obtain its system-assigned managed identity.
# Static machines (registered in the same apply) are excluded — they are not yet
# visible to the data source and will be picked up on the next apply after onboarding.
data "azurerm_arc_machine" "machines" {
  for_each            = local.arc_machines_discovered
  name                = each.key
  resource_group_name = data.azurerm_resource_group.arc_enabled_servers[0].name
}

# Grant each machine's MI the Azure Relay Listener role on its own HC so the relay
# listener service can authenticate without a SAS key.
module "relay_listener_role" {
  for_each = local.arc_machines_discovered
  source   = "../dtos-devops-templates/infrastructure/modules/rbac-assignment"

  scope                = azurerm_relay_hybrid_connection.per_machine[each.key].id
  role_definition_name = "Azure Relay Listener"
  principal_id         = data.azurerm_arc_machine.machines[each.key].identity[0].principal_id
}
