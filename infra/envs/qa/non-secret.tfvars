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

# API, Redis, and the Celery worker all sit at zero replicas by default.
# Scale one up manually when you need it:
#   az containerapp update --name remitx-qa-<app> --resource-group remitx-qa-rg --min-replicas 1
