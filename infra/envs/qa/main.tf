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

module "key_vault" {
  source              = "../../modules/key-vault"
  name                = "relyo-${var.environment}-kv"
  resource_group_name = module.resource_group.name
  location            = module.resource_group.location
  database_url        = module.postgresql.connection_string
  redis_url           = "redis://placeholder:6379/0"
  clerk_secret_key    = var.clerk_secret_key
  xrpl_encryption_key = var.xrpl_encryption_key
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
