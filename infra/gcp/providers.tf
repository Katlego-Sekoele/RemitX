provider "google" {
  project = var.gcp_project_id
  region  = var.gcp_region
  credentials = var.gcloud_application_default_credentials_json != "" && var.gcloud_application_default_credentials_json != null ? var.gcloud_application_default_credentials_json : null
}

provider "google-beta" {
  project = var.gcp_project_id
  region  = var.gcp_region
  credentials = var.gcloud_application_default_credentials_json != "" && var.gcloud_application_default_credentials_json != null ? var.gcloud_application_default_credentials_json : null
}

provider "upstash" {
  email   = var.upstash_email
  api_key = var.upstash_api_key
}

provider "clerk" {
  api_key = var.clerk_secret_key
}
