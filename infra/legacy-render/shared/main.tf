resource "render_project" "remitx" {
  name = "remitx"
  environments = {
    qa = {
      name             = "qa"
      protected_status = "unprotected"
    }
    prod = {
      name             = "production"
      protected_status = "protected"
    }
  }
}

module "keyvalue" {
  source = "./modules/keyvalue"
  name   = "remitx-kv"
  region = var.region
}
