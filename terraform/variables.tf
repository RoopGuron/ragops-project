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

variable "vpc_name" {
  type        = string
  default     = "ragops-vpc"
  description = "The name of the VPC network"
}

variable "k8s_cluster_name" {
  type        = string
  default     = "ragops-cluster"
  description = "The name of the GKE cluster"
}

variable "billing_account_id" {
  type        = string
  description = "The GCP billing account ID"
}

variable "budget_amount" {
  type        = number
  default     = 50
  description = "The budget amount in USD"
}