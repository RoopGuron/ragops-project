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
