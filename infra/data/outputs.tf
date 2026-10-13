output "neon_project_id" {
  value = module.neon.project_id
}

output "qa_branch_id" {
  value = module.neon.qa_branch_id
}

output "prod_branch_id" {
  value = module.neon.prod_branch_id
}

output "database_urls" {
  description = "SQLAlchemy Postgres URLs per deploy environment."
  value = {
    qa   = module.neon.database_url_qa
    prod = module.neon.database_url_prod
  }
  sensitive = true
}
