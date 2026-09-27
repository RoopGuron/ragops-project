resource "google_container_cluster" "ragops_cluster" {
  name     = var.k8s_cluster_name
  location = var.zone

  network          = google_compute_network.vpc_network.name
  subnetwork       = google_compute_subnetwork.subnet.name
  ip_allocation_policy {
    cluster_secondary_range_name  = "pods"
    services_secondary_range_name = "services"
  }

  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  release_channel {
    channel = "REGULAR"
  }

  remove_default_node_pool = true
  initial_node_count = 1

  deletion_protection = false

  depends_on = [
    google_project_service.gcp_services
  ]
}

resource "google_container_node_pool" "ragops_gke_node_pool" {
  name = "ragops-pool"
  cluster = google_container_cluster.ragops_cluster.name
  location = var.zone
  node_count = 2
  node_config {
    machine_type = "e2-standard-4"
    disk_type = "pd-standard"
    disk_size_gb = 50

    # 1. Broadest API access scope for the underlying VM instance
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

}








