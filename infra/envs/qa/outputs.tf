output "api_url" {
  value = "https://${module.api.fqdn}"
}

output "frontend_url" {
  value = "https://${module.static_web_app.default_hostname}"
}
