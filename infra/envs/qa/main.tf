module "resource_group" {
  source   = "../../modules/resource-group"
  name     = "remitx-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}

data "azurerm_subscription" "current" {}

module "budget_alerts" {
  source              = "../../modules/budget-alerts"
  name_prefix         = "remitx-${var.environment}"
  resource_group_name = module.resource_group.name
  resource_group_id   = module.resource_group.id
  subscription_id     = data.azurerm_subscription.current.id
  alert_emails        = var.alert_emails
  monthly_budget_cap  = var.monthly_budget_cap
  budget_start_date   = var.budget_start_date
}

module "application_insights" {
  source              = "../../modules/application-insights"
  name                = "remitx-${var.environment}-ai"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  # Log ingestion is the one charge that survives every replica going to zero,
  # so a paused environment gets a ceiling. See the module variable for what
  # hitting it costs you.
  daily_quota_gb = var.paused ? 0.1 : -1
}

module "container_apps_env" {
  source                     = "../../modules/container-apps-env"
  name                       = "remitx-${var.environment}-cae"
  resource_group_name        = module.resource_group.name
  location                   = module.resource_group.location
  log_analytics_workspace_id = module.application_insights.log_analytics_workspace_id
}

module "redis" {
  source                       = "../../modules/container-app"
  name                         = "remitx-${var.environment}-redis"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = "redis:7-alpine"
  ingress_external             = false
  # Internal TCP ingress, or the api and worker cannot resolve the name at all.
  ingress_internal    = true
  ingress_transport   = "tcp"
  ingress_target_port = 6379
  # Always zero — scale up manually (az containerapp update --min-replicas)
  # when you need it; nothing brings it up on a schedule or on demand.
  min_replicas = 0
  max_replicas = 1
  cpu          = 0.25
  memory       = "0.5Gi"
  paused       = var.paused
}

module "key_vault" {
  source                = "../../modules/key-vault"
  name                  = "remitx-${var.environment}-kv"
  resource_group_name   = module.resource_group.name
  location              = module.resource_group.location
  database_url          = var.database_url
  redis_url             = module.redis.internal_url
  clerk_secret_key      = var.clerk_secret_key
  clerk_publishable_key = var.clerk_publishable_key
  xrpl_encryption_key   = var.xrpl_encryption_key
}

locals {
  # Public image for first ACA revision — deploy.yml pushes GHCR images after apply.
  bootstrap_image = var.bootstrap_container_image

  container_app_secrets = {
    DATABASE_URL        = module.key_vault.secret_ids["database-url"]
    REDIS_URL           = module.key_vault.secret_ids["redis-url"]
    CLERK_SECRET_KEY    = module.key_vault.secret_ids["clerk-secret-key"]
    XRPL_ENCRYPTION_KEY = module.key_vault.secret_ids["xrpl-encryption-key"]
  }

  # Browser origins allowed to call the API. Without this the API falls back to
  # its localhost default and rejects every call from the deployed frontend.
  # Not "*": the API sets allow_credentials, which Starlette refuses to combine
  # with a wildcard.
  cors_origins = join(",", compact([
    var.swa_custom_domain != "" ? "https://${var.swa_custom_domain}" : "",
    "https://${module.static_web_app.default_hostname}",
  ]))

  container_app_env_vars = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = module.application_insights.connection_string
    CORS_ORIGINS                          = local.cors_origins
  }
}

module "api" {
  source                       = "../../modules/container-app"
  name                         = "remitx-${var.environment}-api"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = local.bootstrap_image
  ingress_external             = true
  ingress_target_port          = 4200
  min_replicas                 = var.api_min_replicas
  max_replicas                 = 3
  cpu                          = 0.25
  memory                       = "0.5Gi"
  # The only app here with public ingress, so the only one a passing crawler
  # can bill you for. Pausing removes that wake-up path.
  paused        = var.paused
  key_vault_id  = module.key_vault.id
  secrets       = local.container_app_secrets
  env_vars      = local.container_app_env_vars
  custom_domain = var.api_custom_domain
}

module "worker" {
  source                       = "../../modules/container-app"
  name                         = "remitx-${var.environment}-worker"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = local.bootstrap_image
  ingress_external             = false
  # Always zero — scale up manually (az containerapp update --min-replicas)
  # when you need it; nothing brings it up on a schedule or on demand.
  min_replicas = 0
  max_replicas = 1
  cpu          = 0.25
  memory       = "0.5Gi"
  paused       = var.paused
  key_vault_id = module.key_vault.id
  secrets      = local.container_app_secrets
  env_vars     = local.container_app_env_vars
}

module "static_web_app" {
  source              = "../../modules/static-web-app"
  name                = "remitx-${var.environment}-swa"
  resource_group_name = module.resource_group.name
  location            = var.swa_location
  custom_domain       = var.swa_custom_domain
}
