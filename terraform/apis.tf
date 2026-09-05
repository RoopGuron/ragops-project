locals {
  gcp_services = [
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "billingbudgets.googleapis.com"
  ]
}

resource "google_project_service" "gcp_services" {
  for_each = toset(local.gcp_services)

  project = var.project_id
  service = each.key

  # Recommended: Prevents the API from being disabled when the 
  # Terraform resource is destroyed (which could delete your data)
  disable_on_destroy = false
}
