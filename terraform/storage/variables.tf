variable "project_id" {
  type        = string
  description = "The GCP project ID"
}

variable "region" {
  type        = string
  default     = "us-west1"
  description = "The GCP region"
}

variable "zone" {
  type        = string
  default     = "us-west1-a"
  description = "The GCP zone"
}

variable "bucket_name" {
  type        = string
  default     = "ragops-corpus-sec-filings-roop"
  description = "The name of the GCS Storage Class"
}

variable "storage_class" {
  type        = string
  default     = "STANDARD"
  description = "The name of the GCS Storage Class"
}