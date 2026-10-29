# Authenticate with NEON_API_KEY or var.neon_api_key.
provider "neon" {
  api_key = var.neon_api_key
}

provider "tfe" {
  token = var.tfe_token
}
