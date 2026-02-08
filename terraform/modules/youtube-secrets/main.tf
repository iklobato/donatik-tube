# YouTube multi-account: APIs, Secret Manager secrets, IAM for configurator/worker.

resource "google_project_service" "youtube" {
  project            = var.project_id
  service            = "youtube.googleapis.com"
  disable_on_destroy  = false
}

resource "google_project_service" "secretmanager" {
  project            = var.project_id
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

resource "google_secret_manager_secret" "youtube_oauth_client" {
  project   = var.project_id
  secret_id = "youtube-oauth-client"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "youtube_oauth_client_placeholder" {
  secret      = google_secret_manager_secret.youtube_oauth_client.id
  secret_data = "{}"
}

resource "google_secret_manager_secret_iam_member" "youtube_oauth_client" {
  secret_id = google_secret_manager_secret.youtube_oauth_client.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.service_account_email}"
}

resource "google_secret_manager_secret" "youtube_channel" {
  for_each   = toset(var.youtube_channel_ids)
  project    = var.project_id
  secret_id  = "youtube-channel-${each.value}"

  replication {
    auto {}
  }

  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret_version" "youtube_channel_placeholder" {
  for_each    = toset(var.youtube_channel_ids)
  secret      = google_secret_manager_secret.youtube_channel[each.key].id
  secret_data = "placeholder"
}

resource "google_secret_manager_secret_iam_member" "youtube_channel" {
  for_each   = toset(var.youtube_channel_ids)
  secret_id  = google_secret_manager_secret.youtube_channel[each.key].id
  role       = "roles/secretmanager.secretAccessor"
  member     = "serviceAccount:${var.service_account_email}"
}
