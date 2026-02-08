variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "service_account_id" {
  type        = string
  description = "Service account ID (short name)"
  default     = "streaming-worker"
}
