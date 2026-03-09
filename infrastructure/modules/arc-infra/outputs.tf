output "arc_enabled_servers_resource_group_name" {
  description = "Name of the Arc-enabled servers resource group"
  value       = var.enable_arc_servers ? azurerm_resource_group.arc_enabled_servers[0].name : null
}

output "arc_enabled_servers_resource_group_id" {
  description = "ID of the Arc-enabled servers resource group"
  value       = var.enable_arc_servers ? azurerm_resource_group.arc_enabled_servers[0].id : null
}

output "arc_onboarding_spn_client_id" {
  description = "Client ID of the Arc onboarding service principal"
  value       = var.enable_arc_servers ? data.azuread_service_principal.arc_onboarding[0].client_id : null
}

output "arc_log_analytics_workspace_id" {
  description = "ID of the Arc Log Analytics workspace (null when enable_arc_servers is false)"
  value       = var.enable_arc_servers ? module.log_analytics_workspace[0].id : null
}

output "arc_log_analytics_workspace_name" {
  description = "Name of the Arc Log Analytics workspace (null when enable_arc_servers is false)"
  value       = var.enable_arc_servers ? module.log_analytics_workspace[0].name : null
}

output "relay_namespace_hostname" {
  description = "Relay namespace FQDN for AZURE_RELAY_NAMESPACE in the gateway .env"
  value       = var.enable_arc_servers ? "${local.relay_namespace_name}.servicebus.windows.net" : null
}

output "relay_listen_sas_keys" {
  description = "Per-machine relay listen SAS primary keys, keyed by Arc resource name (SiteCode). Used by the deploy pipeline to write .env files."
  sensitive   = true
  value = var.enable_arc_servers ? {
    for k, rule in azurerm_relay_hybrid_connection_authorization_rule.per_machine_listen :
    k => rule.primary_key
  } : {}
}
