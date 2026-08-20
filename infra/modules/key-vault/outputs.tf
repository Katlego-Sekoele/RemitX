output "id" {
  value = azurerm_key_vault.this.id
}

output "uri" {
  value = azurerm_key_vault.this.vault_uri
}

output "secret_ids" {
  value = {
    "database-url"          = azurerm_key_vault_secret.database_url.versionless_id
    "redis-url"             = azurerm_key_vault_secret.redis_url.versionless_id
    "clerk-secret-key"      = azurerm_key_vault_secret.clerk_secret_key.versionless_id
    "clerk-publishable-key" = azurerm_key_vault_secret.clerk_publishable_key.versionless_id
    "xrpl-encryption-key"   = azurerm_key_vault_secret.xrpl_encryption_key.versionless_id
  }
}
