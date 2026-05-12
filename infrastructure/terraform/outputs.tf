output "app_insights_connection_string" {
  description = "Application Insights connection string for the gateway services"
  sensitive   = true
  value       = module.arc_infra.app_insights_connection_string
}

output "relay_namespace_hostname" {
  description = "Relay namespace FQDN for AZURE_RELAY_NAMESPACE in the gateway .env"
  value       = module.arc_infra.relay_namespace_hostname
}

output "relay_listen_sas_keys" {
  description = "Per-machine relay listen SAS primary keys, keyed by Arc resource name"
  sensitive   = true
  value       = module.arc_infra.relay_listen_sas_keys
}
