# Look up the web API enterprise app that the gateway MIs need to access.
data "azuread_service_principal" "enterprise_app" {
  count        = var.enable_arc_servers ? 1 : 0
  display_name = "spn-manbrs-web-api-${var.env_config}"
}

# Assign the configured app role to each discovered Arc machine's managed identity.
# Static machines are excluded — their MIs are not visible until the next apply after onboarding.
resource "azuread_app_role_assignment" "managed_identity" {
  for_each = local.arc_machines_discovered

  app_role_id         = data.azuread_service_principal.enterprise_app[0].app_role_ids[var.enterprise_app_role_value]
  principal_object_id = data.azurerm_arc_machine.machines[each.key].identity[0].principal_id
  resource_object_id  = data.azuread_service_principal.enterprise_app[0].object_id
}
