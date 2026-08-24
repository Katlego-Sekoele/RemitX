environment  = "qa"
location     = "spaincentral"
swa_location = "eastus2"
tags = {
  project     = "remitx"
  environment = "qa"
}
alert_emails       = ["sekoelekatlego@gmail.com"]
monthly_budget_cap = 5
budget_start_date  = "2026-08-01T00:00:00Z"
api_min_replicas   = 0

api_custom_domain = "qa-api.remitx.tech"
swa_custom_domain = "qa.remitx.tech"

# Container image registry path (GitHub owner/repo). Pipelines set TF_VAR_ghcr_org in CI.
ghcr_org = "katlego-sekoele/remitx"

# Redis and the Celery worker run 20:00–02:00 SAST only; zero replicas for the
# other 18 hours. The API is untouched — it already scales to zero on its own.
scale_schedule = {
  timezone         = "Africa/Johannesburg"
  start            = "0 20 * * *"
  end              = "0 2 * * *"
  desired_replicas = 1
}
