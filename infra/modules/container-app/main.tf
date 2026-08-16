locals {
  use_key_vault_secrets = length(var.secrets) > 0

  secret_names = {
    for env_name in keys(var.secrets) :
    env_name => lower(replace(env_name, "_", "-"))
  }
}

resource "azurerm_container_app" "this" {
  name                         = var.name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = var.container_app_environment_id
  revision_mode                = "Single"

  dynamic "identity" {
    for_each = local.use_key_vault_secrets ? [1] : []
    content {
      type = "SystemAssigned"
    }
  }

  dynamic "secret" {
    for_each = var.secrets
    content {
      name                = local.secret_names[secret.key]
      key_vault_secret_id = secret.value
      identity            = "System"
    }
  }

  dynamic "ingress" {
    for_each = var.ingress_external ? [1] : []
    content {
      external_enabled = true
      target_port      = var.ingress_target_port
      transport        = "auto"

      traffic_weight {
        percentage      = 100
        latest_revision = true
      }
    }
  }

  template {
    min_replicas = var.min_replicas
    max_replicas = var.max_replicas

    container {
      name    = var.name
      image   = var.image
      cpu     = var.cpu
      memory  = var.memory
      command = var.command
      args    = var.args

      dynamic "env" {
        for_each = var.env_vars
        content {
          name  = env.key
          value = env.value
        }
      }

      dynamic "env" {
        for_each = var.secrets
        content {
          name        = env.key
          secret_name = local.secret_names[env.key]
        }
      }
    }
  }

  lifecycle {
    # CI deploy workflows update the image tag after initial provisioning.
    ignore_changes = [secret, template[0].container[0].image]
  }
}

resource "azurerm_role_assignment" "key_vault_secrets_user" {
  count = local.use_key_vault_secrets && var.key_vault_id != null ? 1 : 0

  scope                = var.key_vault_id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_container_app.this.identity[0].principal_id
}

resource "azurerm_container_app_custom_domain" "this" {
  count = var.custom_domain != "" && var.ingress_external ? 1 : 0

  name             = var.custom_domain
  container_app_id = azurerm_container_app.this.id

  lifecycle {
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }
}
