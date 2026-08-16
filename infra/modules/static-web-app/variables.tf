variable "name" {
  type = string
}

variable "resource_group_name" {
  type = string
}

variable "location" {
  type = string
}

variable "custom_domain" {
  type        = string
  default     = ""
  description = "Optional custom domain hostname (e.g. example.com or www.example.com)"
}
