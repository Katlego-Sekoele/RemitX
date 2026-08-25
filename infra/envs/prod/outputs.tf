output "api_url" {
  value = var.api_custom_domain != "" ? "https://${var.api_custom_domain}" : "https://${module.api.fqdn}"
}

output "frontend_url" {
  value = var.swa_custom_domain != "" ? "https://${var.swa_custom_domain}" : "https://${module.static_web_app.default_hostname}"
}

output "api_custom_domain_dns_records" {
  description = "Registrar DNS records for API custom domain verification (prod)"
  sensitive   = true
  value       = module.api.custom_domain_dns_records
}

output "swa_custom_domain_dns_records" {
  description = "Registrar DNS records for frontend custom domain verification (prod)"
  sensitive   = true
  value       = module.static_web_app.custom_domain_dns_records
}

output "static_web_app_deployment_token" {
  description = "Set as GitHub secret AZURE_STATIC_WEB_APPS_API_TOKEN on the matching environment"
  value       = module.static_web_app.api_key
  sensitive   = true
}

output "cost_killswitch_webhook_expiry" {
  description = "Renew (bump webhook_expiry in the budget_killswitch module call and re-apply) before this date or the killswitch stops firing silently. Null when enable_cost_killswitch = false."
  value       = var.enable_cost_killswitch ? module.budget_killswitch[0].webhook_expiry : null
}
