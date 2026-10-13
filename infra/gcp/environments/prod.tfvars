environment = "prod"
git_branch  = "stable"
repo_url    = "https://github.com/Katlego-Sekoele/RemitX"

# gcp_project_id → GitHub variable GCP_PROJECT_ID
gcp_region = "africa-south1"

artifact_registry_repository_id = "remitx"
upstash_primary_region          = "eu-west-1"

frontend_custom_domain = "remitx.tech"
api_custom_domain      = "api.remitx.tech"

object_storage_endpoint_url = "https://br-round-wave-b226igl6.storage.c-6.eu-central-1.aws.neon.tech"
object_storage_bucket       = "remitx-prod-kyc-documents"
object_storage_region       = "eu-central-1"

# billing_account_id, budget_alert_emails → GitHub (prod)

api_container_image    = "gcr.io/cloudrun/hello"
worker_container_image = "gcr.io/cloudrun/hello"

# Same GCP project as QA: point at the deploy SA remitx-gcp-qa created:
github_deploy_service_account_email = "remitx-github-deploy@remitx-gcp.iam.gserviceaccount.com"
