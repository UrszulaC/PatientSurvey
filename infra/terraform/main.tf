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

data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

resource "azurerm_container_group" "survey_app" {
  name                = "survey-app-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  os_type             = "Linux"
  restart_policy      = "Always"

  ip_address_type = "Public"
  dns_name_label  = "survey-app"

  container {
    name  = "survey-app"
    image = "urszulach/epa-feedback-app:latest"
    cpu   = "0.5"
    memory = "1.0"

    ports {
      port     = 8001   # App metrics port
      protocol = "TCP"
    }

    environment_variables = {
      DB_HOST     = azurerm_mssql_server.sql_server.fully_qualified_domain_name
      DB_NAME     = "patient_survey_db"
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
    }
  }
  variable "db_user" {}
  variable "db_password" {}
  
  resource "azurerm_mssql_server" "sql_server" {
    name                         = "survey-sql"
    resource_group_name          = data.azurerm_resource_group.existing.name
    location                     = data.azurerm_resource_group.existing.location
    version                      = "12.0"
    administrator_login          = var.db_user
    administrator_login_password = var.db_password
  }
  
  resource "azurerm_mssql_database" "main" {
    name      = "patient_survey_db"
    server_id = azurerm_mssql_server.sql_server.id
    sku_name  = "Basic"
  }
  
  resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
    name             = "AllowAzureServices"
    server_id        = azurerm_mssql_server.sql_server.id
    start_ip_address = "0.0.0.0"
    end_ip_address   = "0.0.0.0"
  }

  container {
    name  = "node-exporter"
    image = "prom/node-exporter:latest"
    cpu   = "0.1"
    memory = "0.2"

    ports {
      port     = 9100   # Node exporter metrics port
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
