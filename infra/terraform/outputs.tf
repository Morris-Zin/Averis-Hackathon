output "public_url" {
  description = "Public Cloud Run URL for the app and same-origin API."
  value       = google_cloud_run_v2_service.public.uri
}

output "worker_url" {
  description = "Deterministic private Cloud Run worker URL used by both runtimes, Cloud Tasks and Scheduler."
  value       = local.worker_url
}

output "tasks_queue" {
  description = "Full Cloud Tasks queue resource name."
  value       = google_cloud_tasks_queue.runs.id
}

output "tasks_service_account" {
  description = "Service account used to sign Cloud Tasks OIDC requests."
  value       = google_service_account.tasks.email
}

output "secret_names" {
  description = "Secret Manager names to populate before deploying a revision."
  value       = { for key, secret in google_secret_manager_secret.runtime : key => secret.secret_id }
}
