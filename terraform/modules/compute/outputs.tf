output "instance_id" {
  value       = google_compute_instance.vm.instance_id
  description = "Instance ID"
}

output "self_link" {
  value       = google_compute_instance.vm.self_link
  description = "Instance self link"
}

output "network_ip" {
  value       = google_compute_instance.vm.network_interface[0].network_ip
  description = "Private IP of the instance"
}
