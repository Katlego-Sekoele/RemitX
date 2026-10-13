# Instance API singleton. Import before apply:
#   terraform import 'clerk_application_settings.this[0]' application_settings
resource "clerk_application_settings" "this" {
  count = var.manage_clerk_domains ? 1 : 0

  enable_organizations = var.clerk_enable_organizations
  admin_delete_enabled = var.clerk_admin_delete_enabled
}
