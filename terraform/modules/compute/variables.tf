variable "project_id" {
  type        = string
  description = "GCP project ID"
}

variable "zone" {
  type        = string
  description = "GCP zone"
}

variable "network_self_link" {
  type        = string
  description = "VPC network self link"
}

variable "subnetwork_self_link" {
  type        = string
  description = "Subnet self link"
}

variable "machine_type" {
  type        = string
  description = "Machine type (e.g. n2-standard-4)"
  default     = "n2-standard-4"
}

variable "service_account_email" {
  type        = string
  description = "Service account email for the VM"
  default     = ""
}
