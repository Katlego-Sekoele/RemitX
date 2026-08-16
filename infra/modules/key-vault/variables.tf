variable "name" {
  type = string
}

variable "location" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "database_url" {
  type      = string
  sensitive = true
}

variable "redis_url" {
  type = string
}

variable "clerk_secret_key" {
  type      = string
  sensitive = true
}

variable "clerk_publishable_key" {
  type = string
}

variable "clerk_jwks_url" {
  type = string
}

variable "xrpl_encryption_key" {
  type      = string
  sensitive = true
}

variable "deployer_object_id" {
  type        = string
  default     = null
  description = "Object ID of the Terraform deployer (e.g. GitHub OIDC service principal); grants Key Vault Secrets Officer"
}
