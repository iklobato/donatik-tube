# Prod environment: wire root modules with variables.
# Run from this directory: terraform init && terraform plan -var-file=terraform.tfvars

terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}

module "network" {
  source      = "../../modules/network"
  project_id  = var.project_id
  region      = var.region
}

module "iam" {
  source     = "../../modules/iam"
  project_id = var.project_id
}

module "compute" {
  source                 = "../../modules/compute"
  project_id             = var.project_id
  zone                   = var.zone
  network_self_link     = module.network.network_self_link
  subnetwork_self_link  = module.network.subnetwork_self_link
  service_account_email = module.iam.service_account_email
}

module "cloud_sql" {
  source      = "../../modules/cloud-sql"
  project_id  = var.project_id
  region      = var.region
  network_id  = module.network.network_self_link
}
