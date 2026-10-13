resource "upstash_redis_database" "this" {
  database_name  = "remitx-${var.environment}"
  region         = "global"
  primary_region = var.primary_region
  tls            = true
}

locals {
  redis_url = "rediss://default:${upstash_redis_database.this.password}@${upstash_redis_database.this.endpoint}"
}
