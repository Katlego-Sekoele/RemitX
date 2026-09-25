variable "name" {
  type = string
}

variable "repo_url" {
  type = string
}

variable "branch" {
  type = string
}

variable "environment_id" {
  type = string
}

variable "root_directory" {
  type    = string
  default = "frontend"
}

# build:site adds the Storybook product docs at /storybook/, which the admin
# app's Docs page (/admin/docs) embeds.
variable "build_command" {
  type    = string
  default = "npm ci && npm run build:site"
}

variable "publish_path" {
  type    = string
  default = "build/client"
}

variable "env_vars" {
  type    = map(string)
  default = {}
}

variable "custom_domain" {
  type    = string
  default = ""
}
