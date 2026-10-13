output "project_id" {
  value = neon_project.this.id
}

output "qa_branch_id" {
  value = neon_branch.qa.id
}

output "prod_branch_id" {
  value = neon_branch.prod.id
}

output "database_url_qa" {
  value     = local.database_url_qa
  sensitive = true
}

output "database_url_prod" {
  value     = local.database_url_prod
  sensitive = true
}
