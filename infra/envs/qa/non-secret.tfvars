environment = "qa"
location    = "spaincentral"
tags = {
  project     = "remitx"
  environment = "qa"
}
alert_emails       = ["sekoelekatlego@gmail.com"]
monthly_budget_cap = 20
budget_start_date  = "2026-08-01T00:00:00Z"
api_min_replicas   = 0

# Container image registry path (GitHub owner/repo). Pipelines set TF_VAR_ghcr_org in CI.
ghcr_org = "Katlego-Sekoele/RemitX"

# Pipeline service connection principal or your user object ID (see infra/README.md).
azure_deployer_object_id = "42df4cf9-0efa-43ac-8252-2fb56d845bf2"
