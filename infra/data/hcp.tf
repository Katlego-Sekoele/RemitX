data "tfe_workspace" "data" {
  name         = "remitx-data"
  organization = var.hcp_organization
}

data "tfe_workspace" "gcp_qa" {
  name         = "remitx-gcp-qa"
  organization = var.hcp_organization
}

data "tfe_workspace" "gcp_prod" {
  name         = "remitx-gcp-prod"
  organization = var.hcp_organization
}

resource "tfe_workspace_settings" "data" {
  workspace_id        = data.tfe_workspace.data.id
  execution_mode      = "remote"
  global_remote_state = false
  remote_state_consumer_ids = toset([
    data.tfe_workspace.gcp_qa.id,
    data.tfe_workspace.gcp_prod.id,
  ])
}
