output "api_url" {
  value = local.api_public
}

output "worker_url" {
  value = module.worker.service_url
}

output "frontend_url" {
  value = local.frontend_public
}

output "neon_branch_id" {
  value = (
    var.environment == "qa"
    ? data.terraform_remote_state.data.outputs.qa_branch_id
    : data.terraform_remote_state.data.outputs.prod_branch_id
  )
}

output "redis_url" {
  value     = local.redis_url
  sensitive = true
}

output "api_env_vars" {
  value     = local.api_env
  sensitive = true
}

output "worker_env_vars" {
  value     = local.worker_env
  sensitive = true
}

output "vite_env" {
  value = {
    VITE_API_URL               = local.api_public
    VITE_SITE_URL              = local.frontend_public
    VITE_CLERK_PUBLISHABLE_KEY = var.clerk_publishable_key
  }
}

output "api_container_image" {
  value = var.api_container_image
}

output "worker_container_image" {
  value = var.worker_container_image
}

output "artifact_registry_repository" {
  value = google_artifact_registry_repository.remitx.name
}

output "github_deploy_service_account_email" {
  value       = local.github_deploy_email
  description = "GitHub Actions deploy SA — issue GOOGLE_CREDENTIALS for this email after the first apply."
}
