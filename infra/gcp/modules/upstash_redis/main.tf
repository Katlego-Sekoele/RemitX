resource "upstash_redis_database" "this" {
  database_name  = "remitx-${var.environment}"
  region         = "global"
  primary_region = var.primary_region
  tls            = true
}

locals {
  # Celery's Redis backend refuses a rediss:// URL that omits ssl_cert_reqs.
  redis_url = "rediss://default:${upstash_redis_database.this.password}@${upstash_redis_database.this.endpoint}?ssl_cert_reqs=CERT_NONE"
}
