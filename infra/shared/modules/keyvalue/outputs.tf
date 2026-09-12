output "id" {
  value = render_keyvalue.this.id
}

output "internal_connection_string" {
  value     = render_keyvalue.this.connection_info.internal_connection_string
  sensitive = true
}

output "external_connection_string" {
  value     = render_keyvalue.this.connection_info.external_connection_string
  sensitive = true
}
