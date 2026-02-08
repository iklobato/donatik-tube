output "service_account_email" {
  value       = google_service_account.worker.email
  description = "Service account email for VM and Cloud SQL Auth Proxy"
}
