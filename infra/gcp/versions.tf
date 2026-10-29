terraform {
  required_version = ">= 1.16.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    upstash = {
      source  = "upstash/upstash"
      version = "~> 1.5"
    }
    clerk = {
      source  = "buildwithdeck/clerk"
      version = "~> 0.3"
    }
  }
}
