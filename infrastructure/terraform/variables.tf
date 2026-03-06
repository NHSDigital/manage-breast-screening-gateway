variable "app_short_name" {
  description = "Application short name used in resource naming (e.g., mbsgw)"
  type        = string
}

variable "environment" {
  description = "Application environment name (e.g., dev, pr-123)"
  type        = string
}

variable "env_config" {
  description = "Environment configuration name shared across environments (e.g., dev, review)"
  type        = string
}

variable "hub_subscription_id" {
  # Used as the backend subscription_id in terraform-init and by the azurerm.hub provider.
  # Passed via TF_VAR_hub_subscription_id in terraform-init.
  description = "ID of the hub Azure subscription (Terraform state storage and infra Key Vault)"
  type        = string
}

variable "enable_arc_servers" {
  description = "Whether to create Arc-enabled server resource groups and role assignments"
  type        = bool
  default     = true
}

variable "enable_gateway_test_vm" {
  description = "Whether to deploy the gateway test VM environment (VNet, Bastion, NAT GW, Log Analytics, Windows VM)"
  type        = bool
  default     = false
}

variable "vnet_address_space" {
  description = "Address space for the gateway test VM VNet (e.g., 10.130.0.0/16). Required when enable_gateway_test_vm is true."
  type        = string
  default     = null
}

variable "bastion_sku" {
  description = "SKU tier for Azure Bastion (Basic or Standard)"
  type        = string
  default     = "Standard"
}

variable "gateway_test_vm_size" {
  description = "SKU size for the gateway test VM"
  type        = string
  default     = "Standard_B2s"
}

locals {
  region              = "uksouth"
  resource_group_name = "rg-${var.app_short_name}-${var.environment}-uks"
}
