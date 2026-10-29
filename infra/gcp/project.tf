locals {
  enabled_apis = [
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "firebase.googleapis.com",
    "firebasehosting.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "this" {
  for_each = toset(local.enabled_apis)

  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}

# One Artifact Registry repo per GCP project. Prod that reuses the QA project
# (github_deploy_service_account_email set) looks up the existing repo.
resource "google_artifact_registry_repository" "remitx" {
  count = var.github_deploy_service_account_email == "" ? 1 : 0

  location      = var.gcp_region
  repository_id = var.artifact_registry_repository_id
  description   = "RemitX API and worker images (${var.environment})"
  format        = "DOCKER"

  depends_on = [google_project_service.this]
}

data "google_artifact_registry_repository" "remitx" {
  count = var.github_deploy_service_account_email != "" ? 1 : 0

  project       = var.gcp_project_id
  location      = var.gcp_region
  repository_id = var.artifact_registry_repository_id
}

locals {
  artifact_registry_repository_name = (
    var.github_deploy_service_account_email != ""
    ? data.google_artifact_registry_repository.remitx[0].name
    : google_artifact_registry_repository.remitx[0].name
  )
}
