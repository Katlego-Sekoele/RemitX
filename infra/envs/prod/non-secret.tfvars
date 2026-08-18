environment = "prod"
location    = "spaincentral"
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
ghcr_org = "Katlego-Sekoele/RemitX"

# Pipeline service connection principal or your user object ID (see infra/README.md).
azure_deployer_object_id = "34e5788b-0531-4b7a-ac2b-d8d7bc5eff3e"
