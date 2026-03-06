output "resource_group_name" {
  description = "Name of the gateway test VM resource group"
  value       = azurerm_resource_group.main.name
}

output "vnet_id" {
  description = "ID of the gateway test VM VNet"
  value       = module.vnet.vnet.id
}

output "arc_servers_subnet_id" {
  description = "ID of the Arc servers subnet"
  value       = module.subnet_arc_servers.id
}

output "log_analytics_workspace_id" {
  description = "ID of the Log Analytics workspace"
  value       = module.log_analytics_workspace.id
}

output "log_analytics_workspace_name" {
  description = "Name of the Log Analytics workspace"
  value       = module.log_analytics_workspace.name
}

output "gateway_test_vm_name" {
  description = "Name of the gateway test VM"
  value       = module.gateway_test_vm.name
}
