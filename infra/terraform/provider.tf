# provider.tf
provider "azurerm" {
  features {}
  
  # Use Azure CLI authentication instead of service principal
  use_cli = true
  
  # Optional: If you know your subscription ID, you can set it here
  subscription_id = "f8710f06-734a-4570-941f-8a779d917b29"
}
