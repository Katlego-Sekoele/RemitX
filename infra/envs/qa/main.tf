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
