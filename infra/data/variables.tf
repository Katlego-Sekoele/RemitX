variable "hcp_organization" {
  type        = string
  description = "HCP Terraform org. Same as TF_CLOUD_ORGANIZATION."
}

variable "neon_api_key" {
  type        = string
  sensitive   = true
  description = "Neon account API key (NEON_API_KEY)."
}

variable "tfe_token" {
  type        = string
  sensitive   = true
  description = "HCP Terraform API token for workspace settings."
}

variable "neon_org_id" {
  type        = string
  description = "Neon organization id (Account settings). Required when creating projects."
}

# Set after console creation, then import into Terraform (see README).
variable "neon_project_id" {
  type        = string
  description = "Existing Neon project id (for import: terraform import module.neon.neon_project.this <id>)."
}

variable "database_url_qa_override" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Until Neon endpoints are imported, pass TF_VAR_database_url_qa_override from GitHub."
}

variable "database_url_prod_override" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Until Neon endpoints are imported, pass TF_VAR_database_url_prod_override from GitHub."
}

variable "neon_qa_branch_name" {
  type        = string
  default     = "qa"
  description = "Neon Postgres branch name for QA (not a git branch)."
}

variable "neon_prod_branch_name" {
  type        = string
  default     = "main"
  description = "Neon Postgres branch name for production (not a git branch)."
}

variable "qa_role_name" {
  type        = string
  default     = ""
  description = "Postgres role on QA branch; enables Terraform-built DATABASE_URL when set."
}

variable "prod_role_name" {
  type        = string
  default     = ""
  description = "Postgres role on prod branch; enables Terraform-built DATABASE_URL when set."
}

variable "qa_database_name" {
  type    = string
  default = "neondb"
}

variable "prod_database_name" {
  type    = string
  default = "neondb"
}
