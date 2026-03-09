output "relay_namespace_hostname" {
  description = "Relay namespace FQDN for AZURE_RELAY_NAMESPACE in the gateway .env"
  value       = module.arc_infra.relay_namespace_hostname
}

output "relay_listen_sas_keys" {
  description = "Per-machine relay listen SAS primary keys, keyed by Arc resource name (SiteCode)"
  sensitive   = true
  value       = module.arc_infra.relay_listen_sas_keys
}
