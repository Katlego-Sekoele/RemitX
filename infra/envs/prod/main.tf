data "terraform_remote_state" "shared" {
  backend = "remote"
  config = {
    hostname     = "app.terraform.io"
    organization = var.hcp_organization
    workspaces = {
      name = "remitx-shared"
    }
  }
}

locals {
  redis_base = trimsuffix(
    data.terraform_remote_state.shared.outputs.keyvalue_internal_connection_string,
    "/",
  )
  redis_url = "${local.redis_base}/${var.redis_db}"
  # Predicted onrender hosts avoid a frontend ↔ API cycle when custom
  # domains are empty. Render's url output is still exposed for DNS.
  api_public = (
    var.api_custom_domain != ""
    ? "https://${var.api_custom_domain}"
    : "https://remitx-${var.environment}-api.onrender.com"
  )
  frontend_public = (
    var.frontend_custom_domain != ""
    ? "https://${var.frontend_custom_domain}"
    : "https://remitx-${var.environment}-web.onrender.com"
  )
  # Custom domain and the onrender host are both valid browser
  # origins. Using only one rejects the other (the Azure stack
  # already listed both; the Render port dropped that).
  cors_origins = join(",", compact(concat(
    [
      var.frontend_custom_domain != "" ? "https://${var.frontend_custom_domain}" : "",
      "https://remitx-${var.environment}-web.onrender.com",
    ],
    [for origin in split(",", var.additional_cors_origins) : trimspace(origin)],
  )))
  environment_id = (
    var.environment == "prod"
    ? data.terraform_remote_state.shared.outputs.prod_environment_id
    : data.terraform_remote_state.shared.outputs.qa_environment_id
  )

  runtime_env = {
    DATABASE_URL        = var.database_url
    REDIS_URL           = local.redis_url
    CLERK_SECRET_KEY    = var.clerk_secret_key
    XRPL_ENCRYPTION_KEY = var.xrpl_encryption_key
    CELERY_QUEUE        = "settlement"
    # Explicit because Celery's default is the host's core count (8 here),
    # which has nothing to do with the free instance's 512 MB. Each pool
    # process imports remitx_api and costs ~100 MB.
    CELERY_CONCURRENCY = "2"
  }

  # Public chain identity. The encrypted seed is not in this map: only the
  # worker signs, so it is added on worker_env alone.
  xrpl_env = {
    XRPL_TESTNET_URL           = var.xrpl_testnet_url
    UCTUSD_ISSUER              = var.uctusd_issuer
    UCTUSD_CURRENCY_CODE_HEX   = var.uctusd_currency_code_hex
    UCTUSD_CURRENCY_CODE       = var.uctusd_currency_code
    UCTUSD_TRUST_LIMIT         = var.uctusd_trust_limit
    UCTUSD_DISTRIBUTOR_ADDRESS = var.uctusd_distributor_address
    PLATFORM_WALLET_ADDRESS    = var.platform_wallet_address
  }

  # Quote and limit settings are read by the API. The worker never prices a send.
  quote_env = {
    EXCHANGE_RATE_API_KEY        = var.exchange_rate_api_key
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

  worker_env = merge(local.runtime_env, local.xrpl_env, {
    PLATFORM_WALLET_SEED_ENCRYPTED = var.platform_wallet_seed_encrypted
  })

  # One map for the module and the api_env_vars output. The service ignores
  # env_vars after creation, so the output is what actually reaches Render;
  # a hand-kept copy there silently dropped keys.
  api_env = merge(local.runtime_env, local.xrpl_env, local.quote_env, {
    CORS_ORIGINS    = local.cors_origins
    WORKER_WAKE_URL = "${trimsuffix(module.worker.url, "/")}/health"
    # Only the API signs upload and download URLs; the worker never touches
    # documents, so the bucket credential stays out of its environment.
    OBJECT_STORAGE_ENDPOINT_URL      = var.object_storage_endpoint_url
    OBJECT_STORAGE_BUCKET            = var.object_storage_bucket
    OBJECT_STORAGE_REGION            = var.object_storage_region
    OBJECT_STORAGE_ACCESS_KEY_ID     = var.object_storage_access_key_id
    OBJECT_STORAGE_SECRET_ACCESS_KEY = var.object_storage_secret_access_key
  })
}

module "worker" {
  source          = "./modules/web_service"
  name            = "remitx-${var.environment}-worker"
  region          = var.region
  environment_id  = local.environment_id
  repo_url        = var.repo_url
  branch          = var.git_branch
  dockerfile_path = "./api/Dockerfile.worker"
  docker_context  = "./api"
  env_vars        = local.worker_env
}

module "frontend" {
  source         = "./modules/static_site"
  name           = "remitx-${var.environment}-web"
  repo_url       = var.repo_url
  branch         = var.git_branch
  environment_id = local.environment_id
  env_vars = {
    VITE_API_URL               = local.api_public
    VITE_SITE_URL              = local.frontend_public
    VITE_CLERK_PUBLISHABLE_KEY = var.clerk_publishable_key
  }
  custom_domain = var.frontend_custom_domain
}

module "api" {
  source          = "./modules/web_service"
  name            = "remitx-${var.environment}-api"
  region          = var.region
  environment_id  = local.environment_id
  repo_url        = var.repo_url
  branch          = var.git_branch
  dockerfile_path = "./api/Dockerfile"
  docker_context  = "./api"
  env_vars        = local.api_env
  custom_domain   = var.api_custom_domain
}
