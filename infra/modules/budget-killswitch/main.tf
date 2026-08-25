resource "azurerm_automation_account" "this" {
  name                = "${var.name_prefix}-killswitch"
  resource_group_name = var.resource_group_name
  location            = var.location
  sku_name            = "Basic"

  identity {
    type = "SystemAssigned"
  }
}

# Lets the killswitch's managed identity PATCH the container apps' scale
# settings, and nothing else. Verify this role name still resolves in your
# subscription (`az role definition list --name "Container Apps Contributor"`)
# — Microsoft.App RBAC roles have moved names before.
resource "azurerm_role_assignment" "scale_container_apps" {
  scope                 = var.resource_group_id
  role_definition_name  = "Container Apps Contributor"
  principal_id          = azurerm_automation_account.this.identity[0].principal_id
}

resource "azurerm_automation_runbook" "scale_to_zero" {
  name                    = "${var.name_prefix}-scale-to-zero"
  location                = var.location
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.this.name
  log_verbose             = true
  log_progress            = true
  runbook_type            = "PowerShell72"

  content = templatefile("${path.module}/scale-to-zero.ps1.tftpl", {
    subscription_id          = var.subscription_id
    resource_group_name      = var.resource_group_name
    container_app_names_json = jsonencode(var.container_app_names)
  })
}

# Action Groups can only call a runbook through a webhook — the callback URI
# is returned once at creation and captured into state here.
resource "azurerm_automation_webhook" "scale_to_zero" {
  name                    = "${var.name_prefix}-budget-webhook"
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.this.name
  runbook_name            = azurerm_automation_runbook.scale_to_zero.name
  expiry_time             = var.webhook_expiry
  enabled                 = true
}

# Separate from the billing action group so email alerts at $1-4 stay
# email-only; only a notification that explicitly includes this group's ID
# triggers the shutdown.
resource "azurerm_monitor_action_group" "killswitch" {
  name                = "${var.name_prefix}-killswitch"
  resource_group_name = var.resource_group_name
  short_name          = "remitxkill"

  automation_runbook_receiver {
    name                  = "scale-to-zero"
    automation_account_id = azurerm_automation_account.this.id
    runbook_name          = azurerm_automation_runbook.scale_to_zero.name
    webhook_resource_id   = azurerm_automation_webhook.scale_to_zero.id
    service_uri           = azurerm_automation_webhook.scale_to_zero.uri
    is_global_runbook     = false
  }
}
