# Service account with minimal roles for VM and Cloud SQL access.

resource "google_project_service" "youtube" {
  project           = var.project_id
  service           = "youtube.googleapis.com"
  disable_on_destroy = false
}

resource "google_service_account" "worker" {
  account_id   = var.service_account_id
  project      = var.project_id
  display_name = "Streaming worker VM and overlay API"
}

# Allow VM to act as this account and to use Cloud SQL Client
resource "google_project_iam_member" "cloudsql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_project_iam_member" "logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.worker.email}"
}
