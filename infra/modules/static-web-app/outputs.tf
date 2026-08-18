output "default_hostname" {
  value = azurerm_static_web_app.this.default_host_name
}

output "api_key" {
  value     = azurerm_static_web_app.this.api_key
  sensitive = true
}

output "custom_domain" {
  value = var.custom_domain != "" ? var.custom_domain : null
}

output "custom_domain_validation_type" {
  value = var.custom_domain != "" ? local.custom_domain_validation_type : null
}

output "custom_domain_validation_token" {
  value     = try(azurerm_static_web_app_custom_domain.this[0].validation_token, null)
  sensitive = true
}

output "custom_domain_dns_records" {
  description = "DNS records to create at your registrar before Azure managed TLS can bind"
  sensitive   = true
  value = var.custom_domain != "" ? (
    local.custom_domain_validation_type == "dns-txt-token" ? {
      validation_type = "dns-txt-token"
      txt = {
        name  = "_dnsauth"
        value = try(azurerm_static_web_app_custom_domain.this[0].validation_token, null)
      }
      routing = {
        note   = "After validation, point the apex domain to SWA (ALIAS/ANAME or registrar CNAME flattening)"
        target = azurerm_static_web_app.this.default_host_name
      }
      cname = null
      } : {
      validation_type = "cname-delegation"
      txt             = null
      routing         = null
      cname = {
        name   = var.custom_domain
        target = azurerm_static_web_app.this.default_host_name
      }
    }
  ) : null
}
