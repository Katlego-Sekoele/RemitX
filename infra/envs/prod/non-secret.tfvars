environment = "prod"
region      = "frankfurt"
git_branch  = "stable"
repo_url    = "https://github.com/Katlego-Sekoele/RemitX"
redis_db    = 1

api_custom_domain      = ""
frontend_custom_domain = "remitx.tech"
additional_cors_origins = ""

# Neon Object Storage (KYC documents). The endpoint is filled in once the
# bucket exists — see docs/DEPLOYMENT.md. While it is empty the API starts
# normally and only the KYC document routes answer 503.
object_storage_endpoint_url = ""
object_storage_bucket       = "remitx-prod-kyc-documents"
object_storage_region       = "auto"
