provider "azurerm" {
  features {}
  subscription_id = "f8710f06-734a-4570-941f-8a779d917b29"
}

# Existing resource group (data only)
data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

# Existing public IP
data "azurerm_public_ip" "existing" {
  name                = "survey-vmPublicIP"
  resource_group_name = data.azurerm_resource_group.existing.name
}

# Existing NIC (optional, if you need the private IP)
data "azurerm_network_interface" "existing" {
  name                = "survey-vmVMNic"
  resource_group_name = data.azurerm_resource_group.existing.name
}

# Outputs
output "vm_public_ip" {
  value = data.azurerm_public_ip.existing.ip_address
}

output "vm_private_ip" {
  value = data.azurerm_network_interface.existing.ip_configuration[0].private_ip_address
}

output "nic_id" {
  value = data.azurerm_network_interface.existing.id
}

