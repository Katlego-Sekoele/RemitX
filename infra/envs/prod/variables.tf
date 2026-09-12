variable "environment" {
  type = string
}

variable "region" {
  type    = string
  default = "frankfurt"
}

variable "git_branch" {
  type = string
}

variable "repo_url" {
  type = string
}

variable "redis_db" {
  type        = number
  description = "Logical Redis database on the shared Key Value instance"
}

variable "hcp_organization" {
  type        = string
  description = "HCP Terraform org. Set TF_VAR_hcp_organization to the same value as TF_CLOUD_ORGANIZATION."
}

variable "database_url" {
  type        = string
  sensitive   = true
  description = "Neon Postgres URL (SQLAlchemy form). Pass via TF_VAR_database_url."
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

variable "api_custom_domain" {
  type    = string
  default = ""
}

variable "frontend_custom_domain" {
  type    = string
  default = ""
}

variable "render_api_key" {
  type        = string
  sensitive   = true
  description = "Render API key. HCP remote runs do not inherit RENDER_API_KEY; pass TF_VAR_render_api_key."
}

variable "render_owner_id" {
  type        = string
  sensitive   = true
  description = "Render owner id (usr-… or tea-…). Pass TF_VAR_render_owner_id."
}
