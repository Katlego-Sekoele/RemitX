locals {
  use_key_vault_secrets    = length(var.secrets) > 0
  ingress_enabled          = var.ingress_external || var.ingress_internal
  custom_domain_enabled    = var.custom_domain != "" && var.ingress_external
  managed_certificate_name = "${var.name}-tls"

  secret_names = {
    for env_name in keys(var.secrets) :
    env_name => lower(replace(env_name, "_", "-"))
  }

  # KEDA wants a real cron window, so the closest this can get to "never" is a
  # window that opens for five minutes a year. One 0.25 vCPU replica for those
  # five minutes is ~75 vCPU-seconds against a 180,000-second monthly grant.
  paused_scale_schedule = {
    timezone         = "UTC"
    start            = "0 0 1 1 *"
    end              = "5 0 1 1 *"
    desired_replicas = 1
  }

  effective_scale_schedule = var.paused ? local.paused_scale_schedule : var.scale_schedule
  effective_min_replicas   = var.paused ? 0 : var.min_replicas

  # Read null-safely rather than reaching into effective_scale_schedule from
  # the precondition below. HCL only short-circuits `||` on Terraform 1.11+;
  # on the older versions required_version still allows, the right-hand side
  # is evaluated even when the left proves the schedule is null, and every
  # unscheduled app fails to plan with "attribute from null value". Zero is
  # the no-schedule case, and max_replicas is never below it.
  scheduled_desired_replicas = try(local.effective_scale_schedule.desired_replicas, 0)
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
    min_replicas = local.effective_min_replicas
    max_replicas = var.max_replicas

    # Off-hours shutdown, or an indefinite pause. This is the app's only scale
    # rule when set, which replaces the implicit HTTP/TCP one: outside the
    # window the app holds at zero and no inbound connection can wake it.
    dynamic "custom_scale_rule" {
      for_each = local.effective_scale_schedule != null ? [local.effective_scale_schedule] : []
      content {
        name             = "schedule"
        custom_rule_type = "cron"
        metadata = {
          timezone        = custom_scale_rule.value.timezone
          start           = custom_scale_rule.value.start
          end             = custom_scale_rule.value.end
          desiredReplicas = tostring(custom_scale_rule.value.desired_replicas)
        }
      }
    }

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

    precondition {
      condition     = !(var.paused && var.scale_schedule != null)
      error_message = "paused and scale_schedule both drive the app's one cron rule; set one or the other."
    }

    precondition {
      condition     = local.effective_scale_schedule == null || local.effective_min_replicas == 0
      error_message = "scale_schedule requires min_replicas = 0, or the floor keeps the app running straight through the off-window."
    }

    precondition {
      condition     = var.max_replicas >= local.scheduled_desired_replicas
      error_message = "max_replicas must be at least scale_schedule.desired_replicas, or the schedule cannot reach its target."
    }
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
