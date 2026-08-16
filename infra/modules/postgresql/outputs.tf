output "connection_string" {
  value     = "postgresql+psycopg2://${var.admin_username}:${var.admin_password}@${azurerm_postgresql_flexible_server.this.fqdn}:5432/${var.database_name}?sslmode=require"
  sensitive = true
}
