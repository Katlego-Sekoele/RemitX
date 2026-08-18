output "api_url" {
  value = "https://${module.api.fqdn}"
}

output "frontend_url" {
  value = "https://${module.static_web_app.default_hostname}"
}

output "static_web_app_deployment_token" {
  description = "Set as GitHub secret AZURE_STATIC_WEB_APPS_API_TOKEN on the matching environment"
  value       = module.static_web_app.api_key
  sensitive   = true
}
