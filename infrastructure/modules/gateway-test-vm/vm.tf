data "azurerm_client_config" "current" {}

# Infra Key Vault — created by Bicep in the hub subscription.
# Secrets managed manually: arc-onboarding-spn-client-secret, gateway-test-vm-admin-password.
data "azurerm_key_vault" "infra" {
  provider = azurerm.hub

  name                = "kv-${var.app_short_name}-${var.env_config}-inf"
  resource_group_name = "rg-${var.app_short_name}-${var.env_config}-infra"
}

data "azurerm_key_vault_secret" "arc_onboarding_spn_secret" {
  provider = azurerm.hub

  name         = "arc-onboarding-spn-client-secret"
  key_vault_id = data.azurerm_key_vault.infra.id
}

data "azurerm_key_vault_secret" "vm_admin_password" {
  provider = azurerm.hub

  name         = "gateway-test-vm-admin-password"
  key_vault_id = data.azurerm_key_vault.infra.id
}


module "gateway_test_vm" {
  source  = "Azure/avm-res-compute-virtualmachine/azurerm"
  version = "~> 0.20"

  name                = "vm-${var.app_short_name}-${var.env_config}-uks"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.region

  os_type       = "Windows"
  sku_size      = var.gateway_test_vm_size
  zone          = "1"
  computer_name = "${var.app_short_name}-${var.env_config}"

  account_credentials = {
    admin_credentials = {
      username                          = "arcadmin"
      password                          = data.azurerm_key_vault_secret.vm_admin_password.value
      generate_admin_password_or_ssh_key = false
    }
  }

  # Required by NHSE CCoE policy "Private endpoints for Guest Configuration assignments should be enabled"
  # (policy definition 480d0f91-30af-4a76-9afb-f5710ac52b09, effect Deny).
  # Both spellings must be present — "Nework" is a typo in the policy definition itself.
  tags = {
    EnablePrivateNeworkGC  = "TRUE"
    EnablePrivateNetworkGC = "TRUE"
  }

  source_image_reference = {
    publisher = "MicrosoftWindowsServer"
    offer     = "WindowsServer"
    sku       = "2022-datacenter-azure-edition"
    version   = "latest"
  }

  managed_identities = {
    system_assigned = true
  }

  network_interfaces = {
    network_interface_01 = {
      name = "nic-${var.app_short_name}-${var.env_config}-uks"
      ip_configurations = {
        ip_configuration_01 = {
          name                          = "ipconfig1"
          private_ip_subnet_resource_id = module.subnet_arc_servers.id
          is_primary_ipconfiguration    = true
        }
      }
    }
  }

  extensions = {
    aad_login = {
      name                       = "AADLoginForWindows"
      publisher                  = "Microsoft.Azure.ActiveDirectory"
      type                       = "AADLoginForWindows"
      type_handler_version       = "2.0"
      auto_upgrade_minor_version = true
    }
  }
}

# Runs Arc setup once at VM creation. ignore_changes prevents re-running on an already-enrolled VM.
resource "azurerm_virtual_machine_run_command" "arc_setup" {
  name               = "ArcSetup"
  location           = var.region
  virtual_machine_id = module.gateway_test_vm.resource_id

  source {
    script = file("${path.module}/../../../scripts/powershell/arc-setup.ps1")
  }

  parameter {
    name  = "SubscriptionId"
    value = data.azurerm_client_config.current.subscription_id
  }

  parameter {
    name  = "TenantId"
    value = data.azurerm_client_config.current.tenant_id
  }

  parameter {
    name  = "ResourceGroup"
    value = var.arc_enabled_servers_resource_group
  }

  parameter {
    name  = "Location"
    value = var.region
  }

  parameter {
    name  = "ServicePrincipalId"
    value = var.arc_onboarding_spn_client_id
  }

  # Site identity tags — stamped onto the Arc resource for Terraform HC discovery
  # and ADO pipeline ring targeting. ring0 = test VM only.
  parameter {
    name  = "SiteCode"
    value = "${var.app_short_name}-${var.env_config}"
  }

  parameter {
    name  = "SiteType"
    value = "static"
  }

  parameter {
    name  = "DeploymentRing"
    value = "ring0"
  }

  protected_parameter {
    name  = "ServicePrincipalSecret"
    value = data.azurerm_key_vault_secret.arc_onboarding_spn_secret.value
  }

  lifecycle {
    ignore_changes = [source, parameter, protected_parameter]
  }
}
