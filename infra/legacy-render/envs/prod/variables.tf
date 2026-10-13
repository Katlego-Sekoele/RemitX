variable "environment" {
  type = string
}

variable "region" {
  type    = string
  default = "frankfurt"
}

variable "git_branch" {
  type = string
}

variable "repo_url" {
  type = string

  validation {
    # Render stores the repo URL with any ".git" suffix stripped and the
    # provider returns that normalised form. Terraform compares it against the
    # configured value and fails the apply with "Provider produced inconsistent
    # result after apply" — which names neither the suffix nor this variable,
    # so catch it here instead.
    condition     = !endswith(var.repo_url, ".git")
    error_message = "repo_url must not end in \".git\": Render normalises the suffix away, and Terraform then rejects the provider's result."
  }
}

variable "redis_db" {
  type        = number
  description = "Logical Redis database on the shared Key Value instance"
}

variable "hcp_organization" {
  type        = string
  description = "HCP Terraform org. Set TF_VAR_hcp_organization to the same value as TF_CLOUD_ORGANIZATION."
}

variable "database_url" {
  type        = string
  sensitive   = true
  description = "Neon Postgres URL (SQLAlchemy form). Pass via TF_VAR_database_url."
}

variable "clerk_secret_key" {
  type      = string
  sensitive = true
}

variable "clerk_publishable_key" {
  type = string
}

variable "xrpl_encryption_key" {
  type      = string
  sensitive = true
}

variable "platform_wallet_seed_encrypted" {
  type        = string
  sensitive   = true
  description = "Fernet-encrypted treasury seed. GitHub secret TF_VAR_platform_wallet_seed_encrypted. Worker only."
}

variable "exchange_rate_api_key" {
  type        = string
  sensitive   = true
  description = "exchangerate-api.com key. GitHub secret TF_VAR_exchange_rate_api_key. API only."
}

variable "platform_wallet_address" {
  type        = string
  description = "Treasury XRPL address. GitHub variable TF_VAR_platform_wallet_address."
}

variable "xrpl_testnet_url" {
  type        = string
  description = "XRPL testnet JSON-RPC URL. GitHub variable TF_VAR_xrpl_testnet_url."
}

variable "uctusd_issuer" {
  type        = string
  description = "UCTUSD issuer account. GitHub variable TF_VAR_uctusd_issuer."
}

variable "uctusd_currency_code_hex" {
  type        = string
  description = "On-chain UCTUSD currency code, hex. GitHub variable TF_VAR_uctusd_currency_code_hex."
}

variable "uctusd_currency_code" {
  type        = string
  description = "On-chain UCTUSD currency code, plain text. GitHub variable TF_VAR_uctusd_currency_code."
}

variable "uctusd_trust_limit" {
  type        = string
  description = "Trust-line limit used when opening the treasury trust line. GitHub variable TF_VAR_uctusd_trust_limit."
}

variable "uctusd_distributor_address" {
  type        = string
  description = "UCTUSD distributor address. GitHub variable TF_VAR_uctusd_distributor_address."
}

variable "rate_fixing_interval_hours" {
  type        = string
  description = "Hours a fetched FX rate may be quoted. GitHub variable TF_VAR_rate_fixing_interval_hours."
}

variable "max_rate_staleness_hours" {
  type        = string
  description = "Oldest stored FX rate a quote may fall back to. GitHub variable TF_VAR_max_rate_staleness_hours."
}

variable "quote_ttl_minutes" {
  type        = string
  description = "How long a customer quote is honoured. GitHub variable TF_VAR_quote_ttl_minutes."
}

variable "fixed_fee_zar" {
  type        = string
  description = "Fixed send fee, ZAR. GitHub variable TF_VAR_fixed_fee_zar."
}

variable "percentage_fee_rate" {
  type        = string
  description = "Percentage send fee as a decimal rate. GitHub variable TF_VAR_percentage_fee_rate."
}

variable "fx_margin_rate" {
  type        = string
  description = "FX spread as a decimal rate. GitHub variable TF_VAR_fx_margin_rate."
}

variable "cash_out_fee_rate" {
  type        = string
  description = "Cash-out fee as a decimal rate. GitHub variable TF_VAR_cash_out_fee_rate."
}

variable "min_cash_out_fee" {
  type        = string
  description = "Floor on the cash-out fee, in the withdrawal's currency. GitHub variable TF_VAR_min_cash_out_fee."
}

variable "daily_limit_zar_unverified" {
  type        = string
  description = "Daily send limit for unverified users, ZAR. GitHub variable TF_VAR_daily_limit_zar_unverified."
}

variable "monthly_limit_zar_unverified" {
  type        = string
  description = "Monthly send limit for unverified users, ZAR. GitHub variable TF_VAR_monthly_limit_zar_unverified."
}

variable "daily_limit_zar" {
  type        = string
  description = "Daily send limit for verified users, ZAR. GitHub variable TF_VAR_daily_limit_zar."
}

variable "monthly_limit_zar" {
  type        = string
  description = "Monthly send limit for verified users, ZAR. GitHub variable TF_VAR_monthly_limit_zar."
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
  type        = string
  default     = ""
  description = "Comma-separated browser origins to allow besides the onrender frontend URL and frontend_custom_domain. Use this for DNS/Cloudflare hostnames that are not Render-managed custom domains."
}

variable "render_api_key" {
  type        = string
  sensitive   = true
  description = "Render API key. HCP remote runs do not inherit RENDER_API_KEY; pass TF_VAR_render_api_key."
}

variable "render_owner_id" {
  type        = string
  sensitive   = true
  description = "Render owner id (usr-… or tea-…). Pass TF_VAR_render_owner_id."
}

variable "object_storage_endpoint_url" {
  type        = string
  default     = ""
  description = "S3 endpoint of the Neon Object Storage bucket holding KYC documents. Empty leaves the document routes answering 503 and everything else working."
}

variable "object_storage_bucket" {
  type        = string
  default     = "kyc-documents"
  description = "Bucket KYC documents are uploaded to. Private; never public-read."
}

variable "object_storage_region" {
  type        = string
  default     = "auto"
  description = "Neon ignores the region, but SigV4 requires one in the credential scope."
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

# --- XRPL EVM Testnet (Treasury Wallet) ---
# Optional for now: the GitHub values do not exist yet. An empty value is left
# out of the services' environment rather than set to "".

variable "evm_encryption_key" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Fernet key that decrypts the EVM treasury key. GitHub secret TF_VAR_evm_encryption_key. Worker only."
}

variable "evm_treasury_key_encrypted" {
  type        = string
  sensitive   = true
  default     = ""
  description = "Fernet-encrypted EVM treasury private key. GitHub secret TF_VAR_evm_treasury_key_encrypted. Worker only."
}

variable "evm_treasury_address" {
  type        = string
  default     = ""
  description = "Treasury Wallet EVM address. GitHub variable TF_VAR_evm_treasury_address."
}

variable "evm_rpc_url" {
  type        = string
  default     = ""
  description = "XRPL EVM Testnet JSON-RPC URL. GitHub variable TF_VAR_evm_rpc_url."
}

variable "evm_chain_id" {
  type        = string
  default     = ""
  description = "XRPL EVM Testnet chain id (1449000). GitHub variable TF_VAR_evm_chain_id."
}

variable "evm_explorer_url" {
  type        = string
  default     = ""
  description = "Block explorer base URL. GitHub variable TF_VAR_evm_explorer_url."
}

variable "uctusd_contract_address" {
  type        = string
  default     = ""
  description = "UCTUSD ERC-20 contract address. GitHub variable TF_VAR_uctusd_contract_address."
}

variable "uctusd_evm_decimals" {
  type        = string
  default     = ""
  description = "UCTUSD ERC-20 decimals (18). GitHub variable TF_VAR_uctusd_evm_decimals."
}
