output "name" {
  value = azurerm_container_app.this.name
}

output "fqdn" {
  value = try(azurerm_container_app.this.ingress[0].fqdn, null)
}

output "internal_url" {
  value = "redis://${var.name}:6379/0"
}

output "custom_domain" {
  value = var.custom_domain != "" ? var.custom_domain : null
}

output "custom_domain_verification_id" {
  value = try(azurerm_container_app.this.custom_domain_verification_id, null)
}

output "custom_domain_dns_records" {
  description = "DNS records to create at your registrar before Azure managed TLS can bind"
  value = var.custom_domain != "" && var.ingress_external ? {
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
