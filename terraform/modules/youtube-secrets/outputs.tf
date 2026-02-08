output "youtube_oauth_client_secret_id" {
  value       = google_secret_manager_secret.youtube_oauth_client.secret_id
  description = "Secret Manager secret ID for OAuth client (store client_id and client_secret as JSON)"
}

output "youtube_channel_secret_ids" {
  value       = [for s in google_secret_manager_secret.youtube_channel : s.secret_id]
  description = "Secret Manager secret IDs for per-channel refresh tokens"
}
