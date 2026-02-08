output "cloud_sql_connection_name" {
  value       = module.cloud_sql.connection_name
  description = "Use with Cloud SQL Auth Proxy: --port=5432 <this_value>"
}

output "compute_network_ip" {
  value       = module.compute.network_ip
  description = "Private IP of the streaming VM"
}
