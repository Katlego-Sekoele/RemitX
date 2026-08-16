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
  description = "Key Vault resource ID; required when secrets are set (for RBAC)"
}
