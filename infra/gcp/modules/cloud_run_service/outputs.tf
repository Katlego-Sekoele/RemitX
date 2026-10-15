output "service_url" {
  value = google_cloud_run_v2_service.this.uri
}

output "service_name" {
  value = google_cloud_run_v2_service.this.name
}

output "hosting_url" {
  value = var.custom_domain != "" ? "https://${google_firebase_hosting_site.this[0].site_id}.web.app" : null
}

output "custom_domain_dns" {
  value = one(google_firebase_hosting_custom_domain.this[*].required_dns_updates)
}
