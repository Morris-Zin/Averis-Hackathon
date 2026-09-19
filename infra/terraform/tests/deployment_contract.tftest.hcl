mock_provider "google" {
  override_during = plan

  mock_data "google_project" {
    defaults = {
      number = "808014275060"
    }
  }
}

override_resource {
  target          = google_service_account.tasks
  override_during = plan
  values = {
    email = "averis-tasks@averis-hackathon-509115.iam.gserviceaccount.com"
    name  = "projects/averis-hackathon-509115/serviceAccounts/averis-tasks@averis-hackathon-509115.iam.gserviceaccount.com"
  }
}

variables {
  project_id    = "averis-hackathon-509115"
  image         = "asia-southeast1-docker.pkg.dev/averis-hackathon-509115/averis/averis:test"
  public_origin = "https://averis.example.com"
  r2_endpoint   = "https://example.r2.cloudflarestorage.com"
  r2_bucket     = "averis-documents"
}

run "deployment_contract" {
  command = plan

  assert {
    condition     = output.worker_url == "https://averis-worker-808014275060.asia-southeast1.run.app"
    error_message = "The worker must use Cloud Run's deterministic service URL."
  }

  assert {
    condition = (
      google_cloud_tasks_queue.runs.retry_config[0].max_attempts == -1 &&
      google_cloud_tasks_queue.runs.retry_config[0].max_retry_duration == "3600s"
    )
    error_message = "Delivery retries must be time-bounded without consuming the application's substantive-attempt count."
  }

  assert {
    condition = (
      google_cloud_tasks_queue.runs.http_target[0].oidc_token[0].service_account_email ==
      google_service_account.tasks.email
    )
    error_message = "Cloud Tasks delivery must retain the dedicated OIDC identity."
  }

  assert {
    condition = (
      google_cloud_tasks_queue_iam_member.public_enqueuer.role == "roles/cloudtasks.enqueuer" &&
      google_cloud_tasks_queue_iam_member.worker_enqueuer.role == "roles/cloudtasks.enqueuer"
    )
    error_message = "Both task-producing runtimes must be able to enqueue on the run queue."
  }

  assert {
    condition = (
      google_service_account_iam_member.public_tasks_delivery_act_as.service_account_id == google_service_account.tasks.name &&
      google_service_account_iam_member.worker_tasks_delivery_act_as.service_account_id == google_service_account.tasks.name &&
      google_service_account_iam_member.public_tasks_delivery_act_as.role == "roles/iam.serviceAccountUser" &&
      google_service_account_iam_member.worker_tasks_delivery_act_as.role == "roles/iam.serviceAccountUser"
    )
    error_message = "Runtime actAs permission must be scoped to the tasks delivery service account."
  }

  assert {
    condition = (
      one([
        for env in google_cloud_run_v2_service.public.template[0].containers[0].env : env.value
        if env.name == "AVERIS_WORKER_URL"
      ]) == output.worker_url &&
      one([
        for env in google_cloud_run_v2_service.worker.template[0].containers[0].env : env.value
        if env.name == "AVERIS_WORKER_URL"
      ]) == output.worker_url
    )
    error_message = "Both runtimes must receive the same deterministic worker URL."
  }

  assert {
    condition = (
      google_cloud_scheduler_job.reconcile.http_target[0].uri == "${output.worker_url}/internal/reconcile" &&
      google_cloud_scheduler_job.reconcile.http_target[0].oidc_token[0].audience == output.worker_url
    )
    error_message = "Scheduler URI and OIDC audience must use the deterministic worker URL."
  }
}
