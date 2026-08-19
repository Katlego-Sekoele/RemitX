locals {
  use_key_vault_secrets    = length(var.secrets) > 0
  ingress_enabled          = var.ingress_external || var.ingress_internal
  custom_domain_enabled    = var.custom_domain != "" && var.ingress_external
  managed_certificate_name = "${var.name}-tls"

  secret_names = {
    for env_name in keys(var.secrets) :
    env_name => lower(replace(env_name, "_", "-"))
  }
}

data "azurerm_client_config" "current" {}

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
    for_each = local.ingress_enabled ? [1] : []
    content {
      external_enabled = var.ingress_external
      target_port      = var.ingress_target_port
      transport        = var.ingress_transport
      # Only meaningful for TCP, where the listening port and the published
      # port are configured separately.
      exposed_port = var.ingress_transport == "tcp" ? var.ingress_target_port : null

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

resource "azurerm_key_vault_access_policy" "container_app" {
  count = local.use_key_vault_secrets ? 1 : 0

  key_vault_id = var.key_vault_id
  tenant_id    = data.azurerm_client_config.current.tenant_id
  object_id    = azurerm_container_app.this.identity[0].principal_id

  secret_permissions = ["Get"]

  depends_on = [azurerm_container_app.this]
}

resource "azurerm_container_app_custom_domain" "this" {
  count = local.custom_domain_enabled ? 1 : 0

  name             = var.custom_domain
  container_app_id = azurerm_container_app.this.id

  lifecycle {
    ignore_changes = [certificate_binding_type, container_app_environment_certificate_id]
  }
}

resource "azurerm_container_app_environment_managed_certificate" "this" {
  count = local.custom_domain_enabled ? 1 : 0

  name                         = local.managed_certificate_name
  container_app_environment_id = var.container_app_environment_id
  subject_name                 = var.custom_domain
  domain_control_validation    = var.custom_domain_tls_validation

  depends_on = [azurerm_container_app_custom_domain.this]
}

# azurerm creates the custom domain and managed cert separately; Azure does not
# always bind them. PATCH the container app ingress so HTTPS works on the hostname.
resource "azapi_resource_action" "custom_domain_tls_binding" {
  count = local.custom_domain_enabled ? 1 : 0

  type        = "Microsoft.App/containerApps@2024-03-01"
  resource_id = azurerm_container_app.this.id
  method      = "PATCH"

  body = {
    properties = {
      configuration = {
        ingress = {
          customDomains = [
            {
              name          = var.custom_domain
              certificateId = azurerm_container_app_environment_managed_certificate.this[0].id
              bindingType   = "SniEnabled"
            }
          ]
        }
      }
    }
  }

  depends_on = [
    azurerm_container_app_custom_domain.this,
    azurerm_container_app_environment_managed_certificate.this,
  ]
}
