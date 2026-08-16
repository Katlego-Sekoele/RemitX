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

variable "clerk_api_key" {
  type        = string
  sensitive   = true
  description = "Clerk Secret Key (sk_test_... or sk_live_...) for this environment's Clerk application"
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
  description = "GitHub repository path for GHCR images (owner/repo), e.g. my-org/Relyo — matches github.repository in deploy workflows"
}

variable "azure_deployer_object_id" {
  type        = string
  description = "Object ID of the GitHub OIDC service principal running Terraform; grants Key Vault Secrets Officer on apply"
}

variable "api_min_replicas" {
  type        = number
  default     = 0
  description = "Minimum API Container App replicas (0 for QA scale-to-zero, 1 for prod)"
}

variable "api_custom_domain" {
  type        = string
  default     = ""
  description = "Optional API custom domain (e.g. api.example.com); wired in a later task"
}

variable "swa_custom_domain" {
  type        = string
  default     = ""
  description = "Optional frontend custom domain (e.g. example.com); wired in a later task"
}
