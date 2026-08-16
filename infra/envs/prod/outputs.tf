output "api_url" {
  value = var.api_custom_domain != "" ? "https://${var.api_custom_domain}" : "https://${module.api.fqdn}"
}

output "frontend_url" {
  value = var.swa_custom_domain != "" ? "https://${var.swa_custom_domain}" : "https://${module.static_web_app.default_hostname}"
}

output "clerk_organization_id" {
  value = module.clerk.organization_id
}

output "api_custom_domain_dns_records" {
  description = "Registrar DNS records for API custom domain verification (prod)"
  value       = module.api.custom_domain_dns_records
}

output "swa_custom_domain_dns_records" {
  description = "Registrar DNS records for frontend custom domain verification (prod)"
  value       = module.static_web_app.custom_domain_dns_records
}
