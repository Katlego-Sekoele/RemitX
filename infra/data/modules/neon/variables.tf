variable "org_id" {
  type = string
}

variable "neon_qa_branch_name" {
  type        = string
  description = "Neon branch name for QA."
}

variable "neon_prod_branch_name" {
  type        = string
  description = "Neon branch name for production."
}

variable "qa_role_name" {
  type        = string
  description = "Postgres role on the QA branch (for connection URI). Set after inspecting Neon."
  default     = ""
}

variable "prod_role_name" {
  type        = string
  description = "Postgres role on the production branch (for connection URI)."
  default     = ""
}

variable "qa_database_name" {
  type    = string
  default = "neondb"
}

variable "prod_database_name" {
  type    = string
  default = "neondb"
}

variable "database_url_qa_override" {
  type      = string
  sensitive = true
  default   = ""
}

variable "database_url_prod_override" {
  type      = string
  sensitive = true
  default   = ""
}
