terraform {
  required_version = ">= 1.16.0"

  required_providers {
    neon = {
      source  = "kislerdm/neon"
      version = "~> 0.18"
    }
    tfe = {
      source  = "hashicorp/tfe"
      version = "~> 0.67"
    }
  }
}
