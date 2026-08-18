environment = "prod"
location    = "spaincentral"
swa_location = "eastus2"
tags = {
  project     = "remitx"
  environment = "prod"
}
alert_emails       = ["sklmae001@myuct.ac.za"]
monthly_budget_cap = 20
budget_start_date  = "2026-08-01T00:00:00Z"
api_min_replicas   = 1

api_custom_domain = "api.remitx.sekoele.co.za"
swa_custom_domain = "remitx.sekoele.co.za"

# Container image registry path (GitHub owner/repo). Pipelines set TF_VAR_ghcr_org in CI.
ghcr_org = "katlego-sekoele/remitx"
