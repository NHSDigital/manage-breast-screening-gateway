terraform {
  required_providers {
    azurerm = {
      source                = "hashicorp/azurerm"
      version               = "4.60.0"
      configuration_aliases = [azurerm.hub]
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "3.4.0"
    }
  }
}
