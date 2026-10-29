environment = "prod"
region      = "frankfurt"
git_branch  = "stable"
repo_url    = "https://github.com/Katlego-Sekoele/RemitX"
redis_db    = 1

api_custom_domain      = ""
frontend_custom_domain = "remitx.tech"
additional_cors_origins = ""

# Neon Object Storage (KYC documents) on the production branch.
object_storage_endpoint_url = "https://br-round-wave-b226igl6.storage.c-6.eu-central-1.aws.neon.tech"
object_storage_bucket       = "remitx-prod-kyc-documents"
object_storage_region       = "eu-central-1"
