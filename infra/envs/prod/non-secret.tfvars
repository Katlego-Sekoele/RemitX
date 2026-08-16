environment = "prod"
location    = "southafricanorth"
tags = {
  project     = "relyo"
  environment = "prod"
}
alert_emails       = ["team@example.com"]
monthly_budget_cap = 20
budget_start_date  = "2026-08-01T00:00:00Z"
api_min_replicas   = 1

api_custom_domain = "api.example.com"
swa_custom_domain = "example.com"

# Set via workflow from github.repository / repository variable in CI.
# For local apply, replace with your GitHub owner/repo path.
ghcr_org = "ORG/Relyo"

# GitHub OIDC service principal object ID (see infra/README.md).
azure_deployer_object_id = "00000000-0000-0000-0000-000000000000"
