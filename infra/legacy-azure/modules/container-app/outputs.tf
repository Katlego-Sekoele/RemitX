output "name" {
  value = azurerm_container_app.this.name
}

output "fqdn" {
  value = try(azurerm_container_app.this.ingress[0].fqdn, null)
}

output "internal_url" {
  description = <<-EOT
    Redis URL for siblings in the same environment. Null unless ingress is
    enabled: without it the name does not resolve, and returning a URL anyway
    hands callers an address that silently fails at runtime.
  EOT
  value       = local.ingress_enabled ? "redis://${var.name}:6379/0" : null
}

output "custom_domain" {
  value = var.custom_domain != "" ? var.custom_domain : null
}

output "custom_domain_verification_id" {
  value = try(azurerm_container_app.this.custom_domain_verification_id, null)
}

output "custom_domain_dns_records" {
  description = "DNS records to create at your registrar before Azure managed TLS can bind"
  sensitive   = true
  value = local.custom_domain_enabled ? {
    txt = {
      name  = "asuid.${var.custom_domain}"
      value = azurerm_container_app.this.custom_domain_verification_id
    }
    cname = {
      name   = var.custom_domain
      target = azurerm_container_app.this.ingress[0].fqdn
    }
  } : null
}

output "custom_domain_managed_certificate_id" {
  description = "Azure managed certificate ID for the custom domain (after DNS validation)"
  value       = try(azurerm_container_app_environment_managed_certificate.this[0].id, null)
}
