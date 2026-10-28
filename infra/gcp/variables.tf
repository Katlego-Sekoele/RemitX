variable "environment" {
  type        = string
  description = "Deploy environment: qa or prod."
  validation {
    condition     = contains(["qa", "prod"], var.environment)
    error_message = "environment must be qa or prod."
  }
}

variable "hcp_organization" {
  type        = string
  default     = ""
  description = "HCP Terraform org. Set via GitHub variable TF_CLOUD_ORGANIZATION or TF_VAR_hcp_organization."
}

variable "gcp_project_id" {
  type        = string
  default     = ""
  description = "GCP project id. Set via GitHub variable GCP_PROJECT_ID or TF_VAR_gcp_project_id."
}

variable "gcp_region" {
  type    = string
  default = "africa-south1"
}

variable "git_branch" {
  type = string
}

variable "repo_url" {
  type = string
}

variable "api_custom_domain" {
  type    = string
  default = ""
}

variable "frontend_custom_domain" {
  type    = string
  default = ""
}

variable "additional_cors_origins" {
  type    = string
  default = ""
}

variable "billing_account_id" {
  type        = string
  default     = ""
  description = "GCP billing account id; required when environment is prod."
}

variable "budget_alert_emails" {
  type        = string
  default     = ""
  description = "Comma-separated emails for GCP budget notifications (prod only)."
}

variable "monthly_budget_amount" {
  type        = number
  default     = 10
  description = "Monthly GCP project spend planning target in USD (alerts only; does not stop billing). Also the segment size for budget alert steps. Neon/Upstash/Clerk are outside this filter."
}

variable "budget_alert_step_usd" {
  type        = number
  default     = 2
  description = "Prod budget emails on each whole-dollar step of project spend (continues past monthly_budget_amount)."
}

variable "budget_alert_coverage_usd" {
  type        = number
  default     = 100
  description = "Keep budget step emails through this monthly project spend (default $2…$100 in $2 steps when target is $10)."
}

variable "upstash_email" {
  type        = string
  description = "Upstash account email (provider auth). GitHub variable TF_VAR_upstash_email."
}

variable "upstash_api_key" {
  type      = string
  sensitive = true
}

variable "upstash_primary_region" {
  type        = string
  default     = "eu-west-1"
  description = "Upstash Redis primary region (GCP compute uses africa-south1)."
}

variable "clerk_secret_key" {
  type      = string
  sensitive = true
}

variable "clerk_publishable_key" {
  type = string
}

variable "database_url" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Fallback when remitx-data remote state is empty; usually from TF_VAR_database_url."
}

variable "xrpl_encryption_key" {
  type      = string
  sensitive = true
}

variable "gcloud_application_default_credentials_json" {
  type        = string
  sensitive   = true
  default     = ""
  description = "GCloud application default credentials JSON (GOOGLE_APPLICATION_CREDENTIALS_JSON)."
}

variable "platform_wallet_seed_encrypted" {
  type      = string
  sensitive = true
}

variable "exchange_rate_api_key" {
  type      = string
  sensitive = true
}

variable "object_storage_endpoint_url" {
  type    = string
  default = ""
}

variable "object_storage_bucket" {
  type    = string
  default = "kyc-documents"
}

variable "object_storage_region" {
  type    = string
  default = "eu-central-1"
}

variable "object_storage_access_key_id" {
  type      = string
  sensitive = true
  default   = ""
}

variable "object_storage_secret_access_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "platform_wallet_address" {
  type    = string
  default = ""
}
variable "xrpl_testnet_url" {
  type    = string
  default = ""
}
variable "uctusd_issuer" {
  type    = string
  default = ""
}
variable "uctusd_currency_code_hex" {
  type    = string
  default = ""
}
variable "uctusd_currency_code" {
  type    = string
  default = ""
}
variable "uctusd_trust_limit" {
  type    = string
  default = ""
}
variable "uctusd_distributor_address" {
  type    = string
  default = ""
}

variable "rate_fixing_interval_hours" {
  type    = string
  default = ""
}
variable "max_rate_staleness_hours" {
  type    = string
  default = ""
}
variable "quote_ttl_minutes" {
  type    = string
  default = ""
}
variable "fixed_fee_zar" {
  type    = string
  default = ""
}
variable "percentage_fee_rate" {
  type    = string
  default = ""
}
variable "fx_margin_rate" {
  type    = string
  default = ""
}
variable "cash_out_fee_rate" {
  type    = string
  default = ""
}
variable "min_cash_out_fee" {
  type    = string
  default = ""
}
variable "daily_limit_zar_unverified" {
  type    = string
  default = ""
}
variable "monthly_limit_zar_unverified" {
  type    = string
  default = ""
}
variable "daily_limit_zar" {
  type    = string
  default = ""
}
variable "monthly_limit_zar" {
  type    = string
  default = ""
}

variable "evm_encryption_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "evm_treasury_key_encrypted" {
  type      = string
  sensitive = true
  default   = ""
}

variable "evm_treasury_address" {
  type    = string
  default = ""
}

variable "evm_rpc_url" {
  type    = string
  default = ""
}

variable "evm_chain_id" {
  type    = string
  default = ""
}

variable "evm_explorer_url" {
  type    = string
  default = ""
}

variable "uctusd_contract_address" {
  type    = string
  default = ""
}

variable "uctusd_evm_decimals" {
  type    = string
  default = ""
}

variable "stokvel_contract_address" {
  type        = string
  default     = "0x2f240705314BB79780522635eA47d20072CB8Fe1"
  description = "StokvelVault on XRPL EVM Testnet (contracts/deployments/xrplEvmTestnet.json). Empty omits it."
}

variable "max_stokvel_members" {
  type        = string
  default     = "3"
  description = "Must equal the deployed contract's maxMembers. Empty omits it."
}

variable "stokvel_sync_start_block" {
  type        = string
  default     = "8995825"
  description = "Deployment block of stokvel_contract_address. Required when that address is set. Empty omits it."
}

variable "evm_stokvel_admin_address" {
  type        = string
  default     = ""
  description = "Vault admin address. Worker only. Empty omits it."
}

variable "evm_stokvel_admin_key_encrypted" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Fernet-encrypted vault admin key (EVM_ENCRYPTION_KEY). Worker secret only."
}

variable "enable_trustmebank" {
  type        = string
  default     = "false"
  description = "ENABLE_TRUSTMEBANK on the API. true turns on TrustMeBank deposits. Set TF_VAR_enable_trustmebank on the GitHub environment and redeploy."

  validation {
    condition     = contains(["true", "false", "1", "0", "yes", "no"], lower(var.enable_trustmebank))
    error_message = "enable_trustmebank must be true or false."
  }
}

variable "api_container_image" {
  type        = string
  description = "Artifact Registry image for the API Cloud Run service."
}

variable "worker_container_image" {
  type        = string
  description = "Artifact Registry image for the worker Cloud Run service."
}

variable "manage_clerk_domains" {
  type        = bool
  default     = false
  description = "Set true after clerk_application_settings is imported into Terraform."
}

variable "clerk_enable_organizations" {
  type    = bool
  default = true
}

variable "clerk_admin_delete_enabled" {
  type    = bool
  default = true
}

variable "artifact_registry_repository_id" {
  type        = string
  default     = "remitx"
  description = "Docker Artifact Registry repo id in gcp_region."
}

variable "github_deploy_service_account_email" {
  type        = string
  default     = ""
  description = <<-EOT
    Principal used by GitHub Actions (GOOGLE_CREDENTIALS). Empty: create remitx-github-deploy in this GCP project.
    Non-empty: use that existing SA (typical on remitx-gcp-prod when QA and prod share one project and remitx-gcp-qa already created it).
  EOT
}
