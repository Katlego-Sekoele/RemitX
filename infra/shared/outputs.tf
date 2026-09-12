output "project_id" {
  value = render_project.remitx.id
}

output "qa_environment_id" {
  value = render_project.remitx.environments["qa"].id
}

output "prod_environment_id" {
  value = render_project.remitx.environments["prod"].id
}

output "keyvalue_internal_connection_string" {
  value     = module.keyvalue.internal_connection_string
  sensitive = true
}

output "keyvalue_id" {
  value = module.keyvalue.id
}
