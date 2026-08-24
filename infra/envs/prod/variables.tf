variable "environment" {
  type = string
}

variable "location" {
  type    = string
  default = "spaincentral"
}

variable "swa_location" {
  type        = string
  default     = "eastus2"
  description = "Azure region for Static Web Apps (limited SKUs; pick a region your subscription can provision — try eastus2, westus2, or centralus)"
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

variable "xrpl_encryption_key" {
  type        = string
  sensitive   = true
  description = "XRPL private key encryption key; pass via TF_VAR_xrpl_encryption_key at apply time"
}

variable "ghcr_org" {
  type        = string
  description = "GitHub repository path for GHCR images (owner/repo) — used by deploy.yml, not Terraform"
}

variable "bootstrap_container_image" {
  type        = string
  default     = "mcr.microsoft.com/k8se/quickstart:latest"
  description = "Public placeholder image for initial Container App create; deploy workflows replace with GHCR"
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

variable "scale_schedule" {
  description = <<-EOT
    Off-hours shutdown for the two apps that would otherwise run 24/7 (redis,
    worker). Null runs them continuously.

    Container Apps bills idle replicas, so an always-on 0.25 vCPU / 0.5 GiB
    replica costs real money doing nothing; these two were 96% of the QA bill.

    Outside the window the environment is genuinely down, not just cheap: the
    API still wakes on HTTP because it scales on requests, but Redis is
    unreachable, so anything that enqueues settlement work fails until the
    window opens.

    `start`/`end` are 5-field cron expressions read in `timezone`; the window
    may wrap midnight.
  EOT

  type = object({
    timezone         = string
    start            = string
    end              = string
    desired_replicas = number
  })
  default = null
}
