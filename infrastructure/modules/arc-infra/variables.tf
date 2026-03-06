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
  description = "Base resource group name — used to derive the Arc-enabled servers RG name"
  type        = string
}

variable "enable_arc_servers" {
  description = "Whether to create Arc-enabled server resource groups and role assignments"
  type        = bool
}
