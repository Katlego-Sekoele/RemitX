locals {
  database_url = coalesce(
    var.database_url != "" ? var.database_url : null,
    try(data.terraform_remote_state.data.outputs.database_urls[var.environment], ""),
  )

  redis_url = module.upstash.redis_url

  api_public = (
    var.api_custom_domain != ""
    ? "https://${var.api_custom_domain}"
    : module.api.service_url
  )

  frontend_public = (
    var.frontend_custom_domain != ""
    ? "https://${var.frontend_custom_domain}"
    : module.firebase.default_url
  )

  cors_origins = join(",", compact(concat(
    [
      var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "",
      module.firebase.default_host,
    ],
    [for origin in split(",", var.additional_cors_origins) : trimspace(origin)],
  )))

  runtime_env = {
    CELERY_QUEUE       = "settlement"
    CELERY_CONCURRENCY = "2"
  }

  xrpl_env = {
    XRPL_TESTNET_URL           = var.xrpl_testnet_url
    UCTUSD_ISSUER              = var.uctusd_issuer
    UCTUSD_CURRENCY_CODE_HEX   = var.uctusd_currency_code_hex
    UCTUSD_CURRENCY_CODE       = var.uctusd_currency_code
    UCTUSD_TRUST_LIMIT         = var.uctusd_trust_limit
    UCTUSD_DISTRIBUTOR_ADDRESS = var.uctusd_distributor_address
    PLATFORM_WALLET_ADDRESS    = var.platform_wallet_address
  }

  # Empty values are dropped. The three stokvel settings default to the
  # testnet deployment, so an unset GitHub variable still deploys them.
  evm_env = { for name, value in {
    EVM_RPC_URL              = var.evm_rpc_url
    EVM_CHAIN_ID             = var.evm_chain_id
    EVM_EXPLORER_URL         = var.evm_explorer_url
    UCTUSD_CONTRACT_ADDRESS  = var.uctusd_contract_address
    UCTUSD_EVM_DECIMALS      = var.uctusd_evm_decimals
    EVM_TREASURY_ADDRESS     = var.evm_treasury_address
    STOKVEL_CONTRACT_ADDRESS = var.stokvel_contract_address
    MAX_STOKVEL_MEMBERS      = var.max_stokvel_members
    STOKVEL_SYNC_START_BLOCK = var.stokvel_sync_start_block
  } : name => value if value != "" }

  # Pause/unpause only. The API must not see the admin address or its key.
  stokvel_admin_env = { for name, value in {
    EVM_STOKVEL_ADMIN_ADDRESS = var.evm_stokvel_admin_address
  } : name => value if value != "" }

  quote_env = {
    RATE_FIXING_INTERVAL_HOURS   = var.rate_fixing_interval_hours
    MAX_RATE_STALENESS_HOURS     = var.max_rate_staleness_hours
    QUOTE_TTL_MINUTES            = var.quote_ttl_minutes
    FIXED_FEE_ZAR                = var.fixed_fee_zar
    PERCENTAGE_FEE_RATE          = var.percentage_fee_rate
    FX_MARGIN_RATE               = var.fx_margin_rate
    CASH_OUT_FEE_RATE            = var.cash_out_fee_rate
    MIN_CASH_OUT_FEE             = var.min_cash_out_fee
    DAILY_LIMIT_ZAR_UNVERIFIED   = var.daily_limit_zar_unverified
    MONTHLY_LIMIT_ZAR_UNVERIFIED = var.monthly_limit_zar_unverified
    DAILY_LIMIT_ZAR              = var.daily_limit_zar
    MONTHLY_LIMIT_ZAR            = var.monthly_limit_zar
  }

  worker_env = merge(
    local.runtime_env, local.xrpl_env, local.evm_env, local.stokvel_admin_env,
  )

  # API only. Redirects follow the deployed frontend so flipping the flag
  # does not send customers back to localhost.
  trustmebank_env = {
    ENABLE_TRUSTMEBANK               = lower(var.enable_trustmebank)
    TRUSTMEBANK_OAUTH_REDIRECT_URI   = "${trimsuffix(local.frontend_public, "/")}/app/accounts/trustmebank/oauth"
    TRUSTMEBANK_PAYMENT_REDIRECT_URI = "${trimsuffix(local.frontend_public, "/")}/app/accounts/trustmebank/return"
  }

  api_env = merge(local.runtime_env, local.xrpl_env, local.evm_env, local.quote_env, local.trustmebank_env, {
    CORS_ORIGINS                = local.cors_origins
    WORKER_WAKE_URL             = "${trimsuffix(module.worker.service_url, "/")}/health"
    OBJECT_STORAGE_ENDPOINT_URL = var.object_storage_endpoint_url
    OBJECT_STORAGE_BUCKET       = var.object_storage_bucket
    OBJECT_STORAGE_REGION       = var.object_storage_region
  })
}
