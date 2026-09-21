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

output "bucket_name" {
  value = google_storage_bucket.corpus.name
}
