variable "environment" {
  type = string
}

variable "location" {
  type    = string
  default = "southafricanorth"
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "alert_emails" {
  type        = list(string)
  description = "Email addresses for per-dollar billing alerts"
}

variable "monthly_budget_cap" {
  type    = number
  default = 20
}

variable "budget_start_date" {
  type        = string
  description = "ISO8601 start date for monthly budgets, e.g. 2026-08-01T00:00:00Z"
}

variable "postgres_admin_password" {
  type        = string
  sensitive   = true
  description = "PostgreSQL admin password; pass via TF_VAR_postgres_admin_password at apply time"
}

variable "database_name" {
  type        = string
  default     = "relyo_qa"
  sensitive   = true
  description = "PostgreSQL database name; override via TF_VAR_database_name if needed"
}

variable "clerk_secret_key" {
  type        = string
  sensitive   = true
  description = "Clerk secret key; pass via TF_VAR_clerk_secret_key at apply time"
}

variable "xrpl_encryption_key" {
  type        = string
  sensitive   = true
  description = "XRPL private key encryption key; pass via TF_VAR_xrpl_encryption_key at apply time"
}

variable "ghcr_org" {
  type        = string
  default     = "ORG"
  description = "GHCR owner/org placeholder for container images (ghcr.io/<org>/relyo-api:qa)"
}
