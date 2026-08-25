module "resource_group" {
  source   = "../../modules/resource-group"
  name     = "remitx-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}

data "azurerm_subscription" "current" {}

module "budget_killswitch" {
  count  = var.enable_cost_killswitch ? 1 : 0
  source = "../../modules/budget-killswitch"

  name_prefix         = "remitx-${var.environment}"
  resource_group_name = module.resource_group.name
  resource_group_id   = module.resource_group.id
  location            = module.resource_group.location
  subscription_id     = data.azurerm_subscription.current.subscription_id

  container_app_names = [
    "remitx-${var.environment}-api",
    "remitx-${var.environment}-redis",
    "remitx-${var.environment}-worker",
  ]
}

module "budget_alerts" {
  source                      = "../../modules/budget-alerts"
  name_prefix                 = "remitx-${var.environment}"
  resource_group_name         = module.resource_group.name
  resource_group_id           = module.resource_group.id
  subscription_id             = data.azurerm_subscription.current.id
  alert_emails                = var.alert_emails
  monthly_budget_cap          = var.monthly_budget_cap
  budget_start_date           = var.budget_start_date
  killswitch_action_group_id  = var.enable_cost_killswitch ? module.budget_killswitch[0].action_group_id : null
}

module "application_insights" {
  source              = "../../modules/application-insights"
  name                = "remitx-${var.environment}-ai"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
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
  # Zero outside var.scale_schedule's window; see the variable's description
  # for what that costs you in reachability.
  min_replicas   = var.scale_schedule != null ? 0 : 1
  max_replicas   = 1
  cpu            = 0.25
  memory         = "0.5Gi"
  scale_schedule = var.scale_schedule
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
  key_vault_id                 = module.key_vault.id
  secrets                      = local.container_app_secrets
  env_vars                     = local.container_app_env_vars
  custom_domain                = var.api_custom_domain
}

module "worker" {
  source                       = "../../modules/container-app"
  name                         = "remitx-${var.environment}-worker"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = local.bootstrap_image
  ingress_external             = false
  min_replicas                 = var.scale_schedule != null ? 0 : 1
  max_replicas                 = 1
  cpu                          = 0.25
  memory                       = "0.5Gi"
  scale_schedule               = var.scale_schedule
  key_vault_id                 = module.key_vault.id
  secrets                      = local.container_app_secrets
  env_vars                     = local.container_app_env_vars
}

module "static_web_app" {
  source              = "../../modules/static-web-app"
  name                = "remitx-${var.environment}-swa"
  resource_group_name = module.resource_group.name
  location            = var.swa_location
  custom_domain       = var.swa_custom_domain
}
