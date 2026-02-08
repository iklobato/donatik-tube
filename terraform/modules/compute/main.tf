# Compute Engine VM (N2/N1); optional GPU can be added via guest_accelerator.

resource "google_compute_instance" "vm" {
  name         = "streaming-worker-vm"
  project      = var.project_id
  zone         = var.zone
  machine_type = var.machine_type

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = 50
    }
  }

  network_interface {
    network    = var.network_self_link
    subnetwork = var.subnetwork_self_link
    access_config {}
  }

  dynamic "service_account" {
    for_each = var.service_account_email != "" ? [1] : []
    content {
      email  = var.service_account_email
      scopes = ["cloud-platform"]
    }
  }

  # Optional: add guest_accelerator for NVIDIA T4/L4 when needed
  # guest_accelerator { type = "nvidia-tesla-t4"; count = 1 }
}
