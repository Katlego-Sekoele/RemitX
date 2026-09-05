variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "container_app_environment_id" {
  type = string
}

variable "image" {
  type = string
}

variable "command" {
  type    = list(string)
  default = null
}

variable "args" {
  type    = list(string)
  default = null
}

variable "ingress_external" {
  type    = bool
  default = false
}

variable "ingress_internal" {
  description = <<-EOT
    Expose the app inside the Container Apps environment only.

    Required for any app that siblings address by name. A Container App with no
    ingress at all has no listener and no internal DNS record, so callers fail
    to resolve it entirely ("Name or service not known") even while the
    container itself is healthy.
  EOT
  type        = bool
  default     = false
}

variable "ingress_transport" {
  description = "auto/http/http2 for web apps, tcp for things like Redis."
  type        = string
  default     = "auto"

  validation {
    condition     = contains(["auto", "http", "http2", "tcp"], var.ingress_transport)
    error_message = "ingress_transport must be one of: auto, http, http2, tcp."
  }
}

variable "ingress_target_port" {
  type    = number
  default = 4200
}

variable "min_replicas" {
  type    = number
  default = 1
}

variable "max_replicas" {
  type    = number
  default = 1
}

variable "cpu" {
  type    = number
  default = 0.25
}

variable "memory" {
  type    = string
  default = "0.5Gi"
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "secrets" {
  type        = map(string)
  default     = {}
  description = "Environment variable name to Key Vault secret versionless ID"
}

variable "key_vault_id" {
  type        = string
  default     = null
  description = "Key Vault resource ID; required when secrets are set (for access policy)"
}

variable "custom_domain" {
  type        = string
  default     = ""
  description = "Optional custom domain hostname (e.g. api.example.com); requires ingress_external = true"
}

variable "custom_domain_tls_validation" {
  type        = string
  default     = "CNAME"
  description = "Domain validation for the ACA managed certificate (CNAME or HTTP). Use CNAME when DNS points at the app FQDN."

  validation {
    condition     = contains(["CNAME", "HTTP"], var.custom_domain_tls_validation)
    error_message = "custom_domain_tls_validation must be CNAME or HTTP."
  }
}

variable "paused" {
  description = <<-EOT
    Park the app at zero replicas and keep it there.

    Container Apps bills replica time rather than requests, so scaling to zero
    only helps while nothing wakes the app — and anything with external ingress
    is woken by whatever crawler finds its hostname. Pausing pins min_replicas
    to 0 and attaches a cron scale rule whose window is shut all but five
    minutes a year. That rule replaces the implicit HTTP/TCP rule, so inbound
    traffic stops scaling the app up at all.

    Ingress, custom domains, and managed certificates stay in place, so
    unpausing is a flag flip rather than a re-provision. While paused the
    hostname answers with a Container Apps error instead of the app.

    Mutually exclusive with scale_schedule — both drive the same scale rule.
  EOT

  type    = bool
  default = false
}

variable "scale_schedule" {
  description = <<-EOT
    Optional cron window during which the app runs; zero replicas outside it.

    Implemented as a KEDA cron scale rule. Defining it replaces the implicit
    HTTP/TCP scale rule, so outside the window nothing wakes the app — not even
    an inbound connection. Requires min_replicas = 0.

    `start`/`end` are 5-field cron expressions read in `timezone` (an IANA
    name, e.g. Africa/Johannesburg). The window may wrap midnight.
  EOT

  type = object({
    timezone         = string
    start            = string
    end              = string
    desired_replicas = number
  })
  default = null
}
