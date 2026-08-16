locals {
  custom_domain_labels          = var.custom_domain != "" ? split(".", var.custom_domain) : []
  custom_domain_is_apex         = length(local.custom_domain_labels) == 2
  custom_domain_validation_type = local.custom_domain_is_apex ? "dns-txt-token" : "cname-delegation"
}

resource "azurerm_static_web_app" "this" {
  name                = var.name
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_tier            = "Free"
  sku_size            = "Free"
}

resource "azurerm_static_web_app_custom_domain" "this" {
  count = var.custom_domain != "" ? 1 : 0

  static_web_app_id = azurerm_static_web_app.this.id
  domain_name       = var.custom_domain
  validation_type   = local.custom_domain_validation_type
}
