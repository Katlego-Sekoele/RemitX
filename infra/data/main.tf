module "neon" {
  source = "./modules/neon"

  org_id                  = var.neon_org_id
  neon_qa_branch_name     = var.neon_qa_branch_name
  neon_prod_branch_name   = var.neon_prod_branch_name
  qa_role_name               = var.qa_role_name
  prod_role_name             = var.prod_role_name
  qa_database_name           = var.qa_database_name
  prod_database_name         = var.prod_database_name
  database_url_qa_override   = var.database_url_qa_override
  database_url_prod_override = var.database_url_prod_override
}
