output "arc_log_analytics_workspace_id" {
  description = "ID of the Arc Log Analytics workspace (null when enable_arc_servers is false)"
  value       = module.arc_infra.arc_log_analytics_workspace_id
}

output "arc_log_analytics_workspace_name" {
  description = "Name of the Arc Log Analytics workspace (null when enable_arc_servers is false)"
  value       = module.arc_infra.arc_log_analytics_workspace_name
}

output "arc_enabled_servers_resource_group_name" {
  description = "Name of the Arc-enabled servers resource group"
  value       = module.arc_infra.arc_enabled_servers_resource_group_name
}

output "arc_enabled_servers_resource_group_id" {
  description = "ID of the Arc-enabled servers resource group"
  value       = module.arc_infra.arc_enabled_servers_resource_group_id
}

output "gateway_test_vm_resource_group_name" {
  description = "Name of the gateway test VM resource group (null when enable_gateway_test_vm is false)"
  value       = var.enable_gateway_test_vm ? module.gateway_test_vm[0].resource_group_name : null
}

output "vnet_id" {
  description = "ID of the gateway test VM VNet (null when enable_gateway_test_vm is false)"
  value       = var.enable_gateway_test_vm ? module.gateway_test_vm[0].vnet_id : null
}

output "arc_servers_subnet_id" {
  description = "ID of the Arc servers subnet (null when enable_gateway_test_vm is false)"
  value       = var.enable_gateway_test_vm ? module.gateway_test_vm[0].arc_servers_subnet_id : null
}

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace (null when enable_gateway_test_vm is false)"
  value       = var.enable_gateway_test_vm ? module.gateway_test_vm[0].log_analytics_workspace_id : null
}

output "gateway_test_vm_name" {
  description = "Name of the gateway test VM (null when enable_gateway_test_vm is false)"
  value       = var.enable_gateway_test_vm ? module.gateway_test_vm[0].gateway_test_vm_name : null
}
