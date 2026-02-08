output "connection_name" {
  value       = google_sql_database_instance.main.connection_name
  description = "Cloud SQL connection name for Auth Proxy"
}

output "private_ip" {
  value       = google_sql_database_instance.main.private_ip_address
  description = "Private IP of the instance"
}
