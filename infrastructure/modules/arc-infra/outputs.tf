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
