variable "name" {
  type = string
}

variable "plan" {
  type    = string
  default = "free"
}

variable "region" {
  type = string
}

variable "environment_id" {
  type = string
}

variable "repo_url" {
  type = string
}

variable "branch" {
  type = string
}

variable "dockerfile_path" {
  type = string
}

variable "docker_context" {
  type    = string
  default = "./api"
}

variable "health_check_path" {
  type    = string
  default = "/health"
}

variable "start_command" {
  type    = string
  default = ""
}

variable "env_vars" {
  type      = map(string)
  default   = {}
  sensitive = true
}

variable "custom_domain" {
  type    = string
  default = ""
}
