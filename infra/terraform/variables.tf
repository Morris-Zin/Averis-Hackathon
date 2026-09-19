variable "project_id" {
  description = "GCP project that owns the Averis services."
  type        = string
}

variable "region" {
  description = "GCP region for Cloud Run, Cloud Tasks and Scheduler."
  type        = string
  default     = "asia-southeast1"
}

variable "service_name" {
  description = "Base name used for Averis resources."
  type        = string
  default     = "averis"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]*[a-z0-9]$", var.service_name)) && length(var.service_name) <= 43
    error_message = "service_name must be 2-43 lowercase letters, digits or hyphens, starting with a letter and ending with a letter or digit."
  }
}

variable "artifact_repository" {
  description = "Artifact Registry repository name."
  type        = string
  default     = "averis"
}

variable "image" {
  description = "Fully qualified, already-pushed container image digest or tag."
  type        = string
}

variable "public_origin" {
  description = "Canonical HTTPS origin for the public app, without a trailing slash."
  type        = string
}

variable "r2_endpoint" {
  description = "Cloudflare R2 S3-compatible endpoint, without credentials."
  type        = string
}

variable "r2_bucket" {
  description = "Private R2 bucket that stores source documents and artifacts."
  type        = string
}

variable "public_max_instances" {
  description = "Configured maximum public Cloud Run instances. This is a scaling guard, not a billing cap."
  type        = number
  default     = 3
}

variable "worker_max_instances" {
  description = "Configured maximum private worker Cloud Run instances."
  type        = number
  default     = 2
}

variable "tasks_queue_name" {
  description = "Short Cloud Tasks queue name."
  type        = string
  default     = "averis-runs"
}

variable "scheduler_timezone" {
  description = "IANA timezone for the reconciler schedule."
  type        = string
  default     = "Asia/Kuala_Lumpur"
}
