resource "google_container_cluster" "ragops_cluster" {
  name     = var.k8s_cluster_name
  location = var.region

  enable_autopilot = true
  network          = google_compute_network.vpc_network.name
  subnetwork       = google_compute_subnetwork.subnet.name
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  deletion_protection = false

  depends_on = [
    google_project_service.gcp_services
  ]
}