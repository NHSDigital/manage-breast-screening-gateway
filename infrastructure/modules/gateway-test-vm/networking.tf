# Virtual network for gateway test VM infrastructure
module "vnet" {
  source = "../dtos-devops-templates/infrastructure/modules/vnet"

  name                = "vnet-${var.app_short_name}-${var.env_config}-uks"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.region
  vnet_address_space  = var.vnet_address_space

  log_analytics_workspace_id                   = module.log_analytics_workspace.id
  monitor_diagnostic_setting_vnet_enabled_logs = ["VMProtectionAlerts"]
  monitor_diagnostic_setting_vnet_metrics      = ["AllMetrics"]
}

# NSG rules for the Bastion subnet per Azure documentation:
# https://learn.microsoft.com/en-us/azure/bastion/bastion-nsg
locals {
  bastion_nsg_rules = [
    {
      name                       = "AllowHttpsInbound"
      priority                   = 120
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "443"
      source_address_prefix      = "Internet"
      destination_address_prefix = "*"
    },
    {
      name                       = "AllowGatewayManagerInbound"
      priority                   = 130
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "443"
      source_address_prefix      = "GatewayManager"
      destination_address_prefix = "*"
    },
    {
      name                       = "AllowAzureLoadBalancerInbound"
      priority                   = 140
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "443"
      source_address_prefix      = "AzureLoadBalancer"
      destination_address_prefix = "*"
    },
    {
      name                       = "AllowBastionHostCommunicationInbound"
      priority                   = 150
      direction                  = "Inbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_ranges    = ["8080", "5701"]
      source_address_prefix      = "VirtualNetwork"
      destination_address_prefix = "VirtualNetwork"
    },
    {
      name                       = "DenyAllInbound"
      priority                   = 1000
      direction                  = "Inbound"
      access                     = "Deny"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
    },
    {
      name                       = "AllowSshRdpOutbound"
      priority                   = 100
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_ranges    = ["22", "3389"]
      source_address_prefix      = "*"
      destination_address_prefix = "VirtualNetwork"
    },
    {
      name                       = "AllowAzureCloudOutbound"
      priority                   = 110
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "Tcp"
      source_port_range          = "*"
      destination_port_range     = "443"
      source_address_prefix      = "*"
      destination_address_prefix = "AzureCloud"
    },
    {
      name                       = "AllowBastionHostCommunicationOutbound"
      priority                   = 120
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_ranges    = ["8080", "5701"]
      source_address_prefix      = "VirtualNetwork"
      destination_address_prefix = "VirtualNetwork"
    },
    {
      name                       = "AllowGetSessionInformationOutbound"
      priority                   = 130
      direction                  = "Outbound"
      access                     = "Allow"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "80"
      source_address_prefix      = "*"
      destination_address_prefix = "Internet"
    },
    {
      name                       = "DenyAllOutbound"
      priority                   = 1000
      direction                  = "Outbound"
      access                     = "Deny"
      protocol                   = "*"
      source_port_range          = "*"
      destination_port_range     = "*"
      source_address_prefix      = "*"
      destination_address_prefix = "*"
    },
  ]
}

# Subnet for Azure Bastion — name must be exactly "AzureBastionSubnet"
# cidrsubnet(vnet/16, 10, 0) → /26 (minimum required for Bastion)
module "subnet_bastion" {
  source = "../dtos-devops-templates/infrastructure/modules/subnet"

  name                             = "AzureBastionSubnet"
  resource_group_name              = azurerm_resource_group.main.name
  vnet_name                        = module.vnet.name
  address_prefixes                 = [cidrsubnet(var.vnet_address_space, 10, 0)]
  location                         = var.region
  create_nsg                       = true
  network_security_group_name      = "nsg-bastion-${var.env_config}-uks"
  network_security_group_nsg_rules = local.bastion_nsg_rules

  log_analytics_workspace_id                                     = module.log_analytics_workspace.id
  monitor_diagnostic_setting_network_security_group_enabled_logs = ["NetworkSecurityGroupEvent", "NetworkSecurityGroupRuleCounter"]
}

# Subnet for the gateway test VM
# cidrsubnet(vnet/16, 8, 1) → /24
module "subnet_arc_servers" {
  source = "../dtos-devops-templates/infrastructure/modules/subnet"

  name                        = "snet-arc-servers-${var.env_config}-uks"
  resource_group_name         = azurerm_resource_group.main.name
  vnet_name                   = module.vnet.name
  address_prefixes            = [cidrsubnet(var.vnet_address_space, 8, 1)]
  location                    = var.region
  create_nsg                  = false
  network_security_group_name = "nsg-arc-servers-${var.env_config}-uks"

  log_analytics_workspace_id                                     = module.log_analytics_workspace.id
  monitor_diagnostic_setting_network_security_group_enabled_logs = []
}

# NAT gateway for outbound internet access from the arc-servers subnet.
# Required because Azure no longer provides default outbound SNAT for new VMs.
# Arc agents need outbound HTTPS to Microsoft endpoints to register and report status.
module "nat_gateway" {
  source = "../dtos-devops-templates/infrastructure/modules/nat-gateway"

  name                = "nat-${var.app_short_name}-${var.env_config}-uks"
  public_ip_name      = "pip-nat-${var.app_short_name}-${var.env_config}-uks"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.region
  subnet_id           = module.subnet_arc_servers.id
}

# Bastion host for Entra ID-authenticated RDP access to the test VM
module "bastion" {
  source = "../dtos-devops-templates/infrastructure/modules/bastion"

  name                = "bas-${var.app_short_name}-${var.env_config}-uks"
  public_ip_name      = "pip-bastion-${var.app_short_name}-${var.env_config}-uks"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.region
  sku                 = var.bastion_sku
  subnet_id           = module.subnet_bastion.id

  log_analytics_workspace_id                      = module.log_analytics_workspace.id
  monitor_diagnostic_setting_bastion_enabled_logs = ["BastionAuditLogs"]
  monitor_diagnostic_setting_bastion_metrics      = ["AllMetrics"]
}
