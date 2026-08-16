output "default_hostname" {
  value = azurerm_static_web_app.this.default_host_name
}

output "api_key" {
  value     = azurerm_static_web_app.this.api_key
  sensitive = true
}
