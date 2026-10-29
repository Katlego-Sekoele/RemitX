resource "render_static_site" "this" {
  name           = var.name
  repo_url       = var.repo_url
  branch         = var.branch
  environment_id = var.environment_id
  root_directory = var.root_directory
  build_command  = var.build_command
  publish_path   = var.publish_path
  auto_deploy_trigger = "off"

  env_vars = {
    for key, value in var.env_vars : key => { value = value }
  }

  routes = [
    {
      source      = "/*"
      destination = "/index.html"
      type        = "rewrite"
    },
  ]

  custom_domains = var.custom_domain == "" ? null : [{ name = var.custom_domain }]
}
