data "terraform_remote_state" "data" {
  backend = "remote"
  config = {
    hostname     = "app.terraform.io"
    organization = var.hcp_organization
    workspaces = {
      name = "remitx-data"
    }
  }
}
