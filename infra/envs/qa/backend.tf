terraform {
  backend "azurerm" {
    resource_group_name  = "remitx-tfstate-rg"
    storage_account_name = "remitxtfstate"
    container_name       = "tfstate"
    key                  = "qa.terraform.tfstate"
  }
}
