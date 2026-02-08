variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "service_account_email" {
  type        = string
  description = "Service account that will read YouTube secrets (e.g. configurator or worker VM)"
}

variable "youtube_channel_ids" {
  type        = list(string)
  description = "YouTube channel IDs; one Secret Manager secret youtube-channel-<id> created per ID"
  default     = []
}
