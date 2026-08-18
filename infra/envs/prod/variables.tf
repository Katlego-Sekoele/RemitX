variable "environment" {
  type = string
}

variable "location" {
  type    = string
  default = "spaincentral"
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

variable "database_url" {
  type        = string
  sensitive   = true
  description = "Neon Postgres connection string; pass via TF_VAR_database_url at apply time"
}

variable "clerk_secret_key" {
  type        = string
  sensitive   = true
  description = "Clerk secret key for Key Vault runtime; pass via TF_VAR_clerk_secret_key at apply time"
}

variable "clerk_publishable_key" {
  type        = string
  description = "Clerk Publishable Key (pk_...) for frontend — stored in Key Vault for later use"
}

variable "clerk_jwks_url" {
  type        = string
  description = "Clerk JWKS URL for JWT verification — stored in Key Vault for later use"
}

variable "xrpl_encryption_key" {
  type        = string
  sensitive   = true
  description = "XRPL private key encryption key; pass via TF_VAR_xrpl_encryption_key at apply time"
}

variable "ghcr_org" {
  type        = string
  description = "GitHub repository path for GHCR images (owner/repo), e.g. my-org/RemitX — matches github.repository in deploy workflows"
}

variable "azure_deployer_object_id" {
  type        = string
  description = "Object ID of the GitHub OIDC service principal running Terraform; grants Key Vault Secrets Officer on apply"
}

variable "api_min_replicas" {
  type        = number
  default     = 1
  description = "Minimum API Container App replicas (0 for QA scale-to-zero, 1 for prod)"
}

variable "api_custom_domain" {
  type        = string
  default     = ""
  description = "Optional API custom domain (e.g. api.example.com); set in prod tfvars"
}

variable "swa_custom_domain" {
  type        = string
  default     = ""
  description = "Optional frontend custom domain (e.g. example.com); set in prod tfvars"
}
