data "google_project" "this" {}

resource "google_storage_bucket" "corpus" {
  name          = var.bucket_name # Must be globally unique
  location      = var.region
  storage_class = var.storage_class

  # Prevents 'terraform destroy' from deleting the bucket if it contains objects
  force_destroy = false

  # Guarantees the bucket can never be made public, and it's free
  public_access_prevention = "enforced"

  # Enables uniform IAM access controls across the bucket
  uniform_bucket_level_access = true
}

resource "google_storage_bucket_iam_member" "corpus_bucket_role" {
  bucket = google_storage_bucket.corpus.name
  role   = "roles/storage.objectViewer"
  member = "principal://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/${data.google_project.this.project_id}.svc.id.goog/subject/ns/kubeflow/sa/pipeline-runner"
}

output "bucket_name" {
  value = google_storage_bucket.corpus.name
}

resource "google_project_iam_member" "monitoring_viewer_grafana" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "principal://iam.googleapis.com/projects/${data.google_project.this.number}/locations/global/workloadIdentityPools/${data.google_project.this.project_id}.svc.id.goog/subject/ns/monitoring/sa/default"
}

resource "google_iam_workload_identity_pool" "github_pool" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
}

resource "google_iam_workload_identity_pool_provider" "github_provider" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
  }
  attribute_condition = "assertion.repository == \"RoopGuron/ragops-project\""
  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "github_ci" {
  project      = var.project_id
  account_id   = "github-ci"
  display_name = "GitHub Actions CI"
}

resource "google_project_iam_member" "github_ci_gke" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.github_ci.email}"
}

resource "google_service_account_iam_member" "github_wif_binding" {
  service_account_id = google_service_account.github_ci.name
  role                = "roles/iam.workloadIdentityUser"
  member              = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_pool.name}/attribute.repository/RoopGuron/ragops-project"
}