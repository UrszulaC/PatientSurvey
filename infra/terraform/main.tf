terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.36"
    }
  }
}

provider "azurerm" {
  features {}
}

resource "random_integer" "suffix" {
  min = 1000
  max = 9999
}

data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

resource "azurerm_container_group" "survey_app" {
  name                = "survey-app-cg"
  location            = data.azurerm_resource_group.existing.location
  resource_group_name = data.azurerm_resource_group.existing.name
  os_type             = "Linux"
  restart_policy      = "OnFailure"

  ip_address {
    type           = "Public"
    dns_name_label = "survey-app-${random_integer.suffix.result}"

    ports {
      port     = 8000
      protocol = "TCP"
    }
  }

  container {
    name  = "survey-app"
    image = "urszulach/epa-feedback-app:latest"

    resources {
      cpu    = 0.5
      memory = "1.0"
    }

    ports {
      port     = 8000
      protocol = "TCP"
    }

    environment_variables = {
      DB_HOST     = "172.17.0.1"
      DB_NAME     = "patient_survey_db"
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
    }
  }
}

variable "db_user" {
  type = string
}

variable "db_password" {
  type      = string
  sensitive = true
}

output "survey_app_fqdn" {
  value = azurerm_container_group.survey_app.fqdn
}
