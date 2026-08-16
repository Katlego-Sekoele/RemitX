data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                       = var.name
  location                   = var.location
  resource_group_name        = var.resource_group_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  rbac_authorization_enabled = true
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  value        = var.database_url
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "redis_url" {
  name         = "redis-url"
  value        = var.redis_url
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "clerk_secret_key" {
  name         = "clerk-secret-key"
  value        = var.clerk_secret_key
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "xrpl_encryption_key" {
  name         = "xrpl-encryption-key"
  value        = var.xrpl_encryption_key
  key_vault_id = azurerm_key_vault.this.id
}
