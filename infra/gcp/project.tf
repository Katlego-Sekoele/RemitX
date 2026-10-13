locals {
  enabled_apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "monitoring.googleapis.com",
    "secretmanager.googleapis.com",
    "cloudbilling.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "this" {
  for_each = toset(local.enabled_apis)

  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_artifact_registry_repository" "remitx" {
  location      = var.gcp_region
  repository_id = var.artifact_registry_repository_id
  description   = "RemitX API and worker images (${var.environment})"
  format        = "DOCKER"

  depends_on = [google_project_service.this]
}
