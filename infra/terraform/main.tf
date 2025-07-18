terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.36"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = "f8710f06-734a-4570-941f-8a779d917b29"
}


# 1) Data sources
data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

data "azurerm_public_ip" "existing" {
  name                = "survey-vmPublicIP"
  resource_group_name = data.azurerm_resource_group.existing.name
}

data "azurerm_network_interface" "existing" {
  name                = "survey-vmVMNic"
  resource_group_name = data.azurerm_resource_group.existing.name
}

# 2) ACR to host images
resource "random_integer" "suffix" {
  min = 1000
  max = 9999
}

resource "azurerm_container_registry" "acr" {
  name                = "patientsurveyacr${random_integer.suffix.result}"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  sku                 = "Standard"
  admin_enabled       = true
}

# 3) Azure Container Instance (ACI)
resource "azurerm_container_group" "survey_app" {
  name                = "survey-app-cg"
  location            = data.azurerm_resource_group.existing.location
  resource_group_name = data.azurerm_resource_group.existing.name
  os_type             = "Linux"
  restart_policy      = "OnFailure"

  # use attribute syntax instead of block
  ip_address = {
    type           = "Public"
    dns_name_label = "survey-app-${random_integer.suffix.result}"
    ports = [
      {
        port     = 8000
        protocol = "TCP"
      }
    ]
  }

  container = [
    {
      name   = "survey-app"
      image  = "urszulach/epa-feedback-app:latest"
      cpu    = "0.5"
      memory = "1.0"

      ports = [
        {
          port     = 8000
          protocol = "TCP"
        }
      ]

      environment_variables = {
        DB_HOST     = "172.17.0.1"
        DB_NAME     = "patient_survey_db"
        DB_USER     = var.db_user
        DB_PASSWORD = var.db_password
      }
    }
  ]

  # to pull from ACR than Docker Hub, uncomment this:
  # image_registry_credential {
  #   server   = azurerm_container_registry.acr.login_server
  #   username = azurerm_container_registry.acr.admin_username
  #   password = azurerm_container_registry.acr.admin_password
  # }
}

# 4) Outputs
output "survey_app_fqdn" {
  value = azurerm_container_group.survey_app.fqdn
}

output "survey_app_public_ip" {
  value = azurerm_container_group.survey_app.ip_address
}
