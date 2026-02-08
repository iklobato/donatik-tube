variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "region" {
  type        = string
  description = "GCP region"
}

variable "db_name" {
  type        = string
  description = "Database name"
  default     = "donate"
}

variable "network_id" {
  type        = string
  description = "VPC network ID for private IP"
}

variable "tier" {
  type        = string
  description = "Cloud SQL tier"
  default     = "db-f1-micro"
}
