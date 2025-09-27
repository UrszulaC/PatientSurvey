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
  use_cli = true
}

data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

resource "azurerm_container_group" "survey_app" {
  name                = "survey-app-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "survey-app"

  container {
    name  = "survey-app"
    // image = "urszulach/epa-feedback-app:latest"
    image = "urszulach/epa-feedback-app:${var.app_image_tag}"
    cpu   = "0.5"
    memory = "1.0"

    ports {
      port     = 8001
      protocol = "TCP"
    }

    environment_variables = {
      FLASK_HOST = "0.0.0.0"
      FLASK_PORT = "8001"
      DB_HOST     = azurerm_mssql_server.sql_server.fully_qualified_domain_name
      DB_NAME     = "patient_survey_db"
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
    }
  }

  container {
    name  = "node-exporter"
    image = "prom/node-exporter:latest"
    cpu   = "0.1"
    memory = "0.2"

    ports {
      port     = 9100
      protocol = "TCP"
    }
  }

  tags = {
    purpose = "EPA Patient Survey App + Node Exporter"
  }
}

output "survey_app_fqdn" {
  value = azurerm_container_group.survey_app.fqdn
}

output "survey_app_public_ip" {
  value = azurerm_container_group.survey_app.ip_address
}
output "docker_user_set" {
  value     = var.docker_user != "" ? "SET" : "MISSING"
  sensitive = false
}

output "docker_password_set" {
  value     = var.docker_password != "" ? "SET" : "MISSING"
  sensitive = false
}

