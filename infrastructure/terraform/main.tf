module "arc_infra" {
  source = "../modules/arc-infra"

  providers = {
    azurerm = azurerm
    azuread = azuread
  }

  region              = local.region
  app_short_name      = var.app_short_name
  env_config          = var.env_config
  resource_group_name = local.resource_group_name
  enable_arc_servers  = var.enable_arc_servers
}

module "gateway_test_vm" {
  count  = var.enable_gateway_test_vm ? 1 : 0
  source = "../modules/gateway-test-vm"

  providers = {
    azurerm     = azurerm
    azurerm.hub = azurerm.hub
    azuread     = azuread
  }

  region               = local.region
  app_short_name       = var.app_short_name
  env_config           = var.env_config
  resource_group_name  = local.resource_group_name
  vnet_address_space   = var.vnet_address_space
  gateway_test_vm_size = var.gateway_test_vm_size
  bastion_sku          = var.bastion_sku

  arc_enabled_servers_resource_group = module.arc_infra.arc_enabled_servers_resource_group_name
  arc_onboarding_spn_client_id       = module.arc_infra.arc_onboarding_spn_client_id
}
