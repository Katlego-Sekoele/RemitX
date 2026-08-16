module "resource_group" {
  source   = "../../modules/resource-group"
  name     = "relyo-${var.environment}-rg"
  location = var.location
  tags     = var.tags
}
