resource "render_web_service" "this" {
  name              = var.name
  plan              = var.plan
  region            = var.region
  environment_id    = var.environment_id
  health_check_path = var.health_check_path
  start_command     = var.start_command == "" ? null : var.start_command

  runtime_source = {
    docker = {
      repo_url            = var.repo_url
      branch              = var.branch
      auto_deploy_trigger = "off"
      dockerfile_path     = var.dockerfile_path
      context             = var.docker_context
    }
  }

  env_vars = {
    for key, value in var.env_vars : key => { value = value }
  }

  custom_domains = var.custom_domain == "" ? null : [{ name = var.custom_domain }]
}
