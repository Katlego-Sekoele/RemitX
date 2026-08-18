resource "azurerm_monitor_action_group" "billing" {
  name                = "${var.name_prefix}-billing"
  resource_group_name = var.resource_group_name
  short_name          = "remitxbill"

  dynamic "email_receiver" {
    for_each = toset(var.alert_emails)
    content {
      name          = replace(email_receiver.value, "@", "-at-")
      email_address = email_receiver.value
    }
  }
}

resource "azurerm_consumption_budget_resource_group" "segment" {
  for_each = local.segments

  name              = "${var.name_prefix}-budget-${each.value.amount}usd"
  resource_group_id = var.resource_group_id

  amount     = each.value.amount
  time_grain = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = each.value.dollars
    content {
      enabled        = true
      threshold = floor((notification.value / each.value.amount) * 100)
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
      contact_groups = [azurerm_monitor_action_group.billing.id]
    }
  }
}

resource "azurerm_consumption_budget_subscription" "segment" {
  for_each = var.enable_subscription_budget ? local.segments : {}

  name            = "${var.name_prefix}-sub-budget-${each.value.amount}usd"
  subscription_id = var.subscription_id
  amount          = each.value.amount
  time_grain      = "Monthly"

  time_period {
    start_date = var.budget_start_date
  }

  dynamic "notification" {
    for_each = each.value.dollars
    content {
      enabled        = true
      threshold = floor((notification.value / each.value.amount) * 100)
      operator       = "GreaterThanOrEqualTo"
      threshold_type = "Actual"
      contact_emails = var.alert_emails
      contact_groups = [azurerm_monitor_action_group.billing.id]
    }
  }
}
