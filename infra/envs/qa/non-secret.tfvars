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

# Parked to stop Azure spend. The API, Redis, and the Celery worker hold at zero
# replicas with nothing left that can wake them, not even a request to the API's
# public hostname. Nothing is destroyed and no data is lost, but the environment
# is off rather than idle: the API answers with a Container Apps error.
#
# Unpause with `paused = false` here, then apply. To bring a single app up for a
# one-off look without unpausing — it lasts only until the next apply:
#   az containerapp update --name remitx-qa-<app> --resource-group remitx-qa-rg --min-replicas 1
paused = true
