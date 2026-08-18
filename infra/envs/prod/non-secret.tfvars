environment = "prod"
location    = "spaincentral"
swa_location = "eastus2"
tags = {
  project     = "remitx"
  environment = "prod"
}
alert_emails       = ["sekoelekatlego@gmail.com"]
monthly_budget_cap = 5
budget_start_date  = "2026-08-01T00:00:00Z"
api_min_replicas   = 0

api_custom_domain = "api.remitx.tech"
swa_custom_domain = "remitx.tech"

# Container image registry path (GitHub owner/repo). Pipelines set TF_VAR_ghcr_org in CI.
ghcr_org = "katlego-sekoele/remitx"
