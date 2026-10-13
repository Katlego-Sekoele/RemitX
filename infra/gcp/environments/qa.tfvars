environment = "qa"
git_branch  = "main"
repo_url    = "https://github.com/Katlego-Sekoele/RemitX"

# gcp_project_id → GitHub variable GCP_PROJECT_ID
gcp_region = "africa-south1"

artifact_registry_repository_id = "remitx"
upstash_primary_region          = "eu-west-1"

frontend_custom_domain  = "qa.remitx.tech"
api_custom_domain       = "qa-api.remitx.tech"
additional_cors_origins = ""

object_storage_endpoint_url = "https://br-divine-union-b2ysf337.storage.c-6.eu-central-1.aws.neon.tech"
object_storage_bucket       = "remitx-qa-kyc-documents"
object_storage_region       = "eu-central-1"

api_container_image    = "gcr.io/cloudrun/hello"
worker_container_image = "gcr.io/cloudrun/hello"
