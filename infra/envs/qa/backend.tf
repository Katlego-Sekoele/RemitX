terraform {
  backend "azurerm" {
    resource_group_name  = "relyo-tfstate-rg"
    storage_account_name = "relyotfstate"
    container_name       = "tfstate"
    key                  = "qa.terraform.tfstate"
  }
}
