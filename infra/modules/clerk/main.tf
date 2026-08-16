resource "clerk_organization" "platform" {
  name = var.organization_name
  slug = var.organization_slug

  public_metadata = jsonencode({
    project     = "relyo"
    environment = var.environment
  })
}
