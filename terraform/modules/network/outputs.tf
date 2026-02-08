output "network_id" {
  value       = google_compute_network.vpc.id
  description = "VPC network ID"
}

output "network_self_link" {
  value       = google_compute_network.vpc.self_link
  description = "VPC network self link"
}

output "subnetwork_self_link" {
  value       = google_compute_subnetwork.subnet.self_link
  description = "Subnet self link"
}
