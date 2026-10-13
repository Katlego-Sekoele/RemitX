# Official provider: https://github.com/neondatabase/terraform-provider-neon
#
# Import (see provider docs):
#   terraform import 'module.neon.neon_project.this' '<project_id>'
#   terraform import 'module.neon.neon_branch.qa' '<project_id>/<qa_branch_id>'
#   terraform import 'module.neon.neon_branch.prod' '<project_id>/<prod_branch_id>'
#   terraform import 'module.neon.neon_endpoint.qa' '<project_id>/<qa_endpoint_id>'
#   terraform import 'module.neon.neon_endpoint.prod' '<project_id>/<prod_endpoint_id>'

resource "neon_project" "this" {
  name   = "RemitX"
  org_id = var.org_id
  history_retention_seconds = 21600 

  lifecycle {
    prevent_destroy = true
  }
}

resource "neon_branch" "qa" {
  project_id = neon_project.this.id
  name       = var.neon_qa_branch_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "neon_branch" "prod" {
  project_id = neon_project.this.id
  name       = var.neon_prod_branch_name

  lifecycle {
    prevent_destroy = true
  }
}

resource "neon_endpoint" "qa" {
  project_id = neon_project.this.id
  branch_id  = neon_branch.qa.id
  type       = "read_write"
}

resource "neon_endpoint" "prod" {
  project_id = neon_project.this.id
  branch_id  = neon_branch.prod.id
  type       = "read_write"
}

data "neon_branch_role_password" "qa" {
  count = var.qa_role_name != "" ? 1 : 0

  project_id = neon_project.this.id
  branch_id  = neon_branch.qa.id
  role_name  = var.qa_role_name
}

data "neon_branch_role_password" "prod" {
  count = var.prod_role_name != "" ? 1 : 0

  project_id = neon_project.this.id
  branch_id  = neon_branch.prod.id
  role_name  = var.prod_role_name
}

locals {
  qa_from_neon = (
    var.qa_role_name != ""
    ? format(
      "postgresql+psycopg2://%s:%s@%s/%s?sslmode=require",
      var.qa_role_name,
      urlencode(data.neon_branch_role_password.qa[0].password),
      neon_endpoint.qa.host,
      var.qa_database_name,
    )
    : ""
  )
  prod_from_neon = (
    var.prod_role_name != ""
    ? format(
      "postgresql+psycopg2://%s:%s@%s/%s?sslmode=require",
      var.prod_role_name,
      urlencode(data.neon_branch_role_password.prod[0].password),
      neon_endpoint.prod.host,
      var.prod_database_name,
    )
    : ""
  )

  database_url_qa = (
    var.database_url_qa_override != "" ? var.database_url_qa_override : local.qa_from_neon
  )
  database_url_prod = (
    var.database_url_prod_override != "" ? var.database_url_prod_override : local.prod_from_neon
  )
}
