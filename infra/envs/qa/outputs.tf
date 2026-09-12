output "api_url" {
  value = var.api_custom_domain != "" ? local.api_public : module.api.url
}

output "api_service_id" {
  value = module.api.id
}

output "worker_url" {
  value = module.worker.url
}

output "worker_service_id" {
  value = module.worker.id
}

output "frontend_url" {
  value = var.frontend_custom_domain != "" ? local.frontend_public : module.frontend.url
}

output "frontend_service_id" {
  value = module.frontend.id
}

output "worker_wake_url" {
  value = "${trimsuffix(module.worker.url, "/")}/health"
}
