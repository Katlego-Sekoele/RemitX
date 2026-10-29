module "upstash" {
  source = "./modules/upstash_redis"

  environment    = var.environment
  region         = "global"
  primary_region = var.upstash_primary_region
}

module "api" {
  source = "./modules/cloud_run_service"

  name                  = "remitx-${var.environment}-api"
  location              = var.gcp_region
  container_image       = var.api_container_image
  service_account_email = google_service_account.api.email
  env                   = local.api_env
  secret_env            = local.api_secret_env
  allow_unauthenticated = true
  min_instance_count    = 0

  depends_on = [
    google_project_service.this,
    google_secret_manager_secret_iam_member.api,
  ]
}

module "worker" {
  source = "./modules/cloud_run_service"

  name                  = "remitx-${var.environment}-worker"
  location              = var.gcp_region
  container_image       = var.worker_container_image
  service_account_email = google_service_account.worker.email
  env                   = local.worker_env
  secret_env            = local.worker_secret_env
  allow_unauthenticated = true
  min_instance_count    = 1
  memory                = "1Gi"

  depends_on = [
    google_project_service.this,
    google_secret_manager_secret_iam_member.worker,
  ]
}

module "firebase" {
  source = "./modules/firebase_site"

  project_id    = var.gcp_project_id
  site_id       = "remitx-${var.environment}-web"
  custom_domain = var.frontend_custom_domain

  depends_on = [google_project_service.this]
}
