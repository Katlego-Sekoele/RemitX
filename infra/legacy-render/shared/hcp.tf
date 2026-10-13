data "tfe_workspace" "shared" {
  name         = "remitx-shared"
  organization = var.hcp_organization
}

data "tfe_workspace" "qa" {
  name         = "remitx-qa"
  organization = var.hcp_organization
}

data "tfe_workspace" "prod" {
  name         = "remitx-prod"
  organization = var.hcp_organization
}

# Env roots read this workspace via terraform_remote_state. HCP denies
# that unless remitx-qa / remitx-prod are listed as consumers.
resource "tfe_workspace_settings" "shared" {
  workspace_id              = data.tfe_workspace.shared.id
  execution_mode            = "remote"
  global_remote_state       = false
  remote_state_consumer_ids = toset([
    data.tfe_workspace.qa.id,
    data.tfe_workspace.prod.id,
  ])
}
