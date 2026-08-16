module "resource_group" {
  source   = "../../modules/resource-group"
  name     = "relyo-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}

data "azurerm_subscription" "current" {}

module "budget_alerts" {
  source              = "../../modules/budget-alerts"
  name_prefix         = "relyo-${var.environment}"
  resource_group_name = module.resource_group.name
  resource_group_id   = module.resource_group.id
  subscription_id     = data.azurerm_subscription.current.id
  alert_emails        = var.alert_emails
  monthly_budget_cap  = var.monthly_budget_cap
  budget_start_date   = var.budget_start_date
}

module "postgresql" {
  source              = "../../modules/postgresql"
  server_name         = "relyo-${var.environment}-pg"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  admin_username      = "relyoadmin"
  admin_password      = var.postgres_admin_password
  database_name       = var.database_name
}

module "application_insights" {
  source              = "../../modules/application-insights"
  name                = "relyo-${var.environment}-ai"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
}

module "container_apps_env" {
  source                     = "../../modules/container-apps-env"
  name                       = "relyo-${var.environment}-cae"
  resource_group_name        = module.resource_group.name
  location                   = module.resource_group.location
  log_analytics_workspace_id = module.application_insights.log_analytics_workspace_id
}

module "redis" {
  source                       = "../../modules/container-app"
  name                         = "relyo-${var.environment}-redis"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = "redis:7-alpine"
  ingress_external             = false
  min_replicas                 = 1
  max_replicas                 = 1
  cpu                          = 0.25
  memory                       = "0.5Gi"
}

module "key_vault" {
  source              = "../../modules/key-vault"
  name                = "relyo-${var.environment}-kv"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  database_url        = module.postgresql.connection_string
  redis_url           = module.redis.internal_url
  clerk_secret_key    = var.clerk_secret_key
  xrpl_encryption_key = var.xrpl_encryption_key
}

locals {
  container_app_secrets = {
    DATABASE_URL        = module.key_vault.secret_ids["database-url"]
    REDIS_URL           = module.key_vault.secret_ids["redis-url"]
    CLERK_SECRET_KEY    = module.key_vault.secret_ids["clerk-secret-key"]
    XRPL_ENCRYPTION_KEY = module.key_vault.secret_ids["xrpl-encryption-key"]
  }
}

module "api" {
  source                       = "../../modules/container-app"
  name                         = "relyo-${var.environment}-api"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = "ghcr.io/${var.ghcr_org}/relyo-api:qa"
  ingress_external             = true
  ingress_target_port          = 4200
  min_replicas                 = 0
  max_replicas                 = 3
  cpu                          = 0.25
  memory                       = "0.5Gi"
  key_vault_id                 = module.key_vault.id
  secrets                      = local.container_app_secrets
}

module "worker" {
  source                       = "../../modules/container-app"
  name                         = "relyo-${var.environment}-worker"
  resource_group_name          = module.resource_group.name
  container_app_environment_id = module.container_apps_env.id
  image                        = "ghcr.io/${var.ghcr_org}/relyo-worker:qa"
  ingress_external             = false
  min_replicas                 = 1
  max_replicas                 = 1
  cpu                          = 0.25
  memory                       = "0.5Gi"
  key_vault_id                 = module.key_vault.id
  secrets                      = local.container_app_secrets
}
