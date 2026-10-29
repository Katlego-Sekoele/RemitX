variable "region" {
  type    = string
  default = "frankfurt"
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

variable "hcp_organization" {
  type        = string
  description = "HCP Terraform org. Set TF_VAR_hcp_organization to the same value as TF_CLOUD_ORGANIZATION."
}

variable "tfe_token" {
  type        = string
  sensitive   = true
  description = "HCP Terraform API token. Pass TF_VAR_tfe_token (same value as TF_API_TOKEN)."
}
