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

variable "xrpl_encryption_key" {
  type      = string
  sensitive = true
}
