resource "google_service_account" "api" {
  account_id   = "remitx-${var.environment}-api"
  display_name = "RemitX ${var.environment} API (Cloud Run)"
}

resource "google_service_account" "worker" {
  account_id   = "remitx-${var.environment}-worker"
  display_name = "RemitX ${var.environment} worker (Cloud Run)"
}

# One deploy SA per GCP project (not per qa/prod workspace). Keys/WIF → GOOGLE_CREDENTIALS.
resource "google_service_account" "github_deploy" {
  count = var.github_deploy_service_account_email == "" ? 1 : 0

  account_id   = "remitx-github-deploy"
  display_name = "RemitX GitHub Actions deploy"
}

data "google_service_account" "github_deploy" {
  count = var.github_deploy_service_account_email != "" ? 1 : 0

  account_id = split("@", var.github_deploy_service_account_email)[0]
  project    = var.gcp_project_id
}

locals {
  github_deploy_email = (
    var.github_deploy_service_account_email != ""
    ? data.google_service_account.github_deploy[0].email
    : google_service_account.github_deploy[0].email
  )
  github_deploy_member = "serviceAccount:${local.github_deploy_email}"

  github_deploy_project_roles = [
    # Terraform runs under this principal in HCP, so it must be able to
    # converge the project as well as perform application rollouts.
    "roles/serviceusage.serviceUsageAdmin",
    "roles/iam.serviceAccountAdmin",
    "roles/resourcemanager.projectIamAdmin",
    "roles/run.admin",
    "roles/artifactregistry.admin",
    "roles/firebase.admin",
    "roles/secretmanager.admin",
  ]
}

resource "google_project_iam_member" "github_deploy" {
  for_each = toset(local.github_deploy_project_roles)

  project = var.gcp_project_id
  role    = each.value
  member  = local.github_deploy_member
}

resource "google_service_account_iam_member" "github_deploy_run_as_api" {
  service_account_id = google_service_account.api.name
  role               = "roles/iam.serviceAccountUser"
  member             = local.github_deploy_member
}

resource "google_service_account_iam_member" "github_deploy_run_as_worker" {
  service_account_id = google_service_account.worker.name
  role               = "roles/iam.serviceAccountUser"
  member             = local.github_deploy_member
}
