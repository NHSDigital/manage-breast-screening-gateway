variable "region" {
  description = "Azure region for all resources"
  type        = string
}

variable "app_short_name" {
  description = "Application short name used in resource naming (e.g., mbsgw)"
  type        = string
}

variable "env_config" {
  description = "Environment configuration name (e.g., dev, review)"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group to create for gateway test VM infrastructure"
  type        = string
}

variable "vnet_address_space" {
  description = "Address space for the VNet (e.g., 10.130.0.0/16)"
  type        = string
}

variable "bastion_sku" {
  description = "SKU tier for Azure Bastion (Basic or Standard)"
  type        = string
}

variable "gateway_test_vm_size" {
  description = "SKU size for the gateway test VM (e.g., Standard_B2s)"
  type        = string
}

variable "arc_enabled_servers_resource_group" {
  description = "Name of the Arc-enabled servers resource group (from arc-infra output) — used as Arc registration target in the onboarding script"
  type        = string
}

variable "arc_onboarding_spn_client_id" {
  description = "Client ID of the Arc onboarding service principal (from arc-infra output)"
  type        = string
}
