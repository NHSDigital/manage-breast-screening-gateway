# The relay namespace is owned by dtos-manage-breast-screening ("manbrs").
# This module creates one Hybrid Connection + listen-only auth rule per Arc-enabled
# machine, auto-discovered by querying the Arc resource group.
# HC names are derived from the Arc resource name (= SiteCode set at onboarding).
#
# Trigger: run `terraform apply` after each Arc onboarding to pick up new machines.

locals {
  relay_namespace_rg   = "rg-manbrs-${var.env_config}-uks"
  relay_namespace_name = "relay-manbrs-${var.env_config}"
}

# Discover all Arc-enabled machines registered in the Arc resource group.
# Each machine's name is the SiteCode set during onboarding (e.g. gw-RVJ-01).
data "azurerm_resources" "arc_machines" {
  count = var.enable_arc_servers ? 1 : 0

  resource_group_name = azurerm_resource_group.arc_enabled_servers[0].name
  type                = "Microsoft.HybridCompute/machines"
}

locals {
  arc_machines = var.enable_arc_servers ? {
    for m in data.azurerm_resources.arc_machines[0].resources : m.name => m
  } : {}
}

# One Hybrid Connection per Arc machine (e.g. hc-gw-RVJ-01).
resource "azurerm_relay_hybrid_connection" "per_machine" {
  for_each = local.arc_machines

  name                          = "hc-${each.key}"
  resource_group_name           = local.relay_namespace_rg
  relay_namespace_name          = local.relay_namespace_name
  requires_client_authorization = true
}

# Listen-only SAS rule per HC — distributed to each gateway site via the deploy pipeline.
# The cloud app uses a namespace-level Send SAS and does not need per-site keys.
resource "azurerm_relay_hybrid_connection_authorization_rule" "per_machine_listen" {
  for_each = local.arc_machines

  name                   = "listen"
  hybrid_connection_name = azurerm_relay_hybrid_connection.per_machine[each.key].name
  namespace_name         = local.relay_namespace_name
  resource_group_name    = local.relay_namespace_rg

  listen = true
  send   = false
  manage = false
}
