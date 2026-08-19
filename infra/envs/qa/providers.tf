terraform {
  required_version = ">= 1.5.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    clerk = {
      source  = "bertie-technology/clerk"
      version = "~> 0.1.0"
    }
    azapi = {
      source  = "Azure/azapi"
      version = "~> 2.0"
    }
  }
}

provider "azurerm" {
  features {}
  resource_provider_registrations = "none"
}

provider "clerk" {
  api_key = var.clerk_api_key
}
