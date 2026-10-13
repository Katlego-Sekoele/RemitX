terraform {
  required_version = ">= 1.5.0"

  cloud {
    # Organization comes from TF_CLOUD_ORGANIZATION (cloud blocks cannot
    # interpolate variables).
    workspaces {
      name = "remitx-prod"
    }
  }

  required_providers {
    render = {
      source  = "render-oss/render"
      version = "1.9.1"
    }
  }
}

# https://registry.terraform.io/providers/render-oss/render/latest/docs
# HCP remote workers do not inherit RENDER_* from GitHub Actions; pass them
# as Terraform variables (TF_VAR_render_api_key / TF_VAR_render_owner_id).
provider "render" {
  api_key                          = var.render_api_key
  owner_id                         = var.render_owner_id
  skip_deploy_after_service_update = true
}
