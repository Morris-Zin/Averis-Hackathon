locals {
  public_service_name = "${var.service_name}-public"
  worker_service_name = "${var.service_name}-worker"
  # Cloud Run's deterministic default URL can be known before the service exists.
  # Keeping this outside the worker resource lets both revisions receive the same
  # worker target without making the worker refer to its own computed URI.
  worker_url = "https://${local.worker_service_name}-${data.google_project.current.number}.${var.region}.run.app"

  secret_env = {
    AVERIS_DATABASE_URL         = "${var.service_name}-database-url"
    AVERIS_R2_ACCESS_KEY_ID     = "${var.service_name}-r2-access-key-id"
    AVERIS_R2_SECRET_ACCESS_KEY = "${var.service_name}-r2-secret-access-key"
    AVERIS_OPERATOR_TOKEN       = "${var.service_name}-operator-token"
    TYPESAFE_API_KEY            = "${var.service_name}-typesafe-api-key"
  }
}

data "google_project" "current" {
  project_id = var.project_id
}

resource "google_project_service" "apis" {
  for_each = toset([
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "cloudtasks.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "container" {
  location      = var.region
  repository_id = var.artifact_repository
  description   = "Averis container images"
  format        = "DOCKER"

  depends_on = [google_project_service.apis]
}

resource "google_service_account" "public" {
  account_id   = "${var.service_name}-public"
  display_name = "Averis public application runtime"
}

resource "google_service_account" "worker" {
  account_id   = "${var.service_name}-worker"
  display_name = "Averis private worker runtime"
}

resource "google_service_account" "tasks" {
  account_id   = "${var.service_name}-tasks"
  display_name = "Averis Cloud Tasks delivery identity"
}

resource "google_service_account" "scheduler" {
  account_id   = "${var.service_name}-scheduler"
  display_name = "Averis reconciler scheduler identity"
}

resource "google_secret_manager_secret" "runtime" {
  for_each  = local.secret_env
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_tasks_queue" "runs" {
  name     = var.tasks_queue_name
  location = var.region

  rate_limits {
    max_dispatches_per_second = 2
    max_concurrent_dispatches = 2
  }

  retry_config {
    # Delivery attempts include transient routing, startup and lease contention.
    # Do not let those consume the three substantive attempts persisted by the app.
    max_attempts       = -1
    min_backoff        = "5s"
    max_backoff        = "60s"
    max_doublings      = 3
    max_retry_duration = "3600s"
  }

  http_target {
    http_method = "POST"

    oidc_token {
      service_account_email = google_service_account.tasks.email
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "public" {
  name                = local.public_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  scaling {
    min_instance_count = 0
    max_instance_count = var.public_max_instances
  }

  template {
    service_account                  = google_service_account.public.email
    timeout                          = "480s"
    max_instance_request_concurrency = 80

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 12
      }

      dynamic "env" {
        for_each = {
          AVERIS_ROLE                  = "web"
          AVERIS_ENV                   = "production"
          AVERIS_ORIGIN                = var.public_origin
          AVERIS_STORAGE_BACKEND       = "r2"
          AVERIS_R2_ENDPOINT           = var.r2_endpoint
          AVERIS_R2_BUCKET             = var.r2_bucket
          AVERIS_TASKS_QUEUE           = google_cloud_tasks_queue.runs.id
          AVERIS_WORKER_URL            = local.worker_url
          AVERIS_TASKS_SERVICE_ACCOUNT = google_service_account.tasks.email
          AVERIS_LIVE_ENABLED          = "false"
        }
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.runtime[env.key].id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service" "worker" {
  name                = local.worker_service_name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  scaling {
    min_instance_count = 0
    max_instance_count = var.worker_max_instances
  }

  template {
    service_account                  = google_service_account.worker.email
    timeout                          = "600s"
    max_instance_request_concurrency = 1

    containers {
      image = var.image

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
      }

      startup_probe {
        http_get {
          path = "/health"
          port = 8080
        }
        initial_delay_seconds = 5
        timeout_seconds       = 3
        period_seconds        = 10
        failure_threshold     = 12
      }

      dynamic "env" {
        for_each = {
          AVERIS_ROLE                  = "worker"
          AVERIS_ENV                   = "production"
          AVERIS_ORIGIN                = var.public_origin
          AVERIS_STORAGE_BACKEND       = "r2"
          AVERIS_R2_ENDPOINT           = var.r2_endpoint
          AVERIS_R2_BUCKET             = var.r2_bucket
          AVERIS_TASKS_QUEUE           = google_cloud_tasks_queue.runs.id
          AVERIS_WORKER_URL            = local.worker_url
          AVERIS_TASKS_SERVICE_ACCOUNT = google_service_account.tasks.email
          AVERIS_LIVE_ENABLED          = "false"
        }
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name = env.key
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.runtime[env.key].id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_cloud_run_v2_service_iam_member" "public_invoker" {
  location = google_cloud_run_v2_service.public.location
  name     = google_cloud_run_v2_service.public.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "tasks_worker_invoker" {
  location = google_cloud_run_v2_service.worker.location
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.tasks.email}"
}

resource "google_cloud_run_v2_service_iam_member" "scheduler_worker_invoker" {
  location = google_cloud_run_v2_service.worker.location
  name     = google_cloud_run_v2_service.worker.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler.email}"
}

resource "google_cloud_tasks_queue_iam_member" "public_enqueuer" {
  project  = var.project_id
  location = google_cloud_tasks_queue.runs.location
  name     = google_cloud_tasks_queue.runs.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.public.email}"
}

resource "google_cloud_tasks_queue_iam_member" "worker_enqueuer" {
  project  = var.project_id
  location = google_cloud_tasks_queue.runs.location
  name     = google_cloud_tasks_queue.runs.name
  role     = "roles/cloudtasks.enqueuer"
  member   = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_service_account_iam_member" "public_tasks_delivery_act_as" {
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.public.email}"
}

resource "google_service_account_iam_member" "worker_tasks_delivery_act_as" {
  service_account_id = google_service_account.tasks.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_secret_manager_secret_iam_member" "public_accessor" {
  for_each  = local.secret_env
  secret_id = google_secret_manager_secret.runtime[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.public.email}"
}

resource "google_secret_manager_secret_iam_member" "worker_accessor" {
  for_each  = local.secret_env
  secret_id = google_secret_manager_secret.runtime[each.key].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.worker.email}"
}

resource "google_cloud_scheduler_job" "reconcile" {
  name             = "${var.service_name}-reconcile"
  region           = var.region
  schedule         = "*/15 * * * *"
  time_zone        = var.scheduler_timezone
  attempt_deadline = "120s"

  retry_config {
    retry_count = 2
  }

  http_target {
    http_method = "POST"
    uri         = "${local.worker_url}/internal/reconcile"
    headers = {
      "Content-Type" = "application/json"
    }
    body = base64encode("{}")

    oidc_token {
      service_account_email = google_service_account.scheduler.email
      audience              = local.worker_url
    }
  }

  depends_on = [
    google_project_service.apis,
    google_cloud_run_v2_service.worker,
    google_cloud_run_v2_service_iam_member.scheduler_worker_invoker,
  ]
}
