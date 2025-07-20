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

data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

resource "random_integer" "suffix" {
  min = 1000
  max = 9999
}

resource "azurerm_container_group" "survey_app" {
  name                = "survey-app-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  os_type             = "Linux"
  restart_policy      = "OnFailure"

  # public IP + DNS
  ip_address_type = "Public"
  dns_name_label  = "survey-app-${random_integer.suffix.result}"

  container {
    name  = "survey-app"
    image = "urszulach/epa-feedback-app:latest"
    cpu   = "0.5"
    memory = "1.0"

    # container-specific port
    ports {
      port     = 8000
      protocol = "TCP"
    }

    environment_variables = {
      DB_HOST     = azurerm_mssql_server.sql_server.fully_qualified_domain_name
      DB_NAME     = "patient_survey_db"
      DB_USER     = var.db_user
      DB_PASSWORD = var.db_password
    }

    # CRITICAL FIX: Add the command to run the Python application
    # This tells the container to execute main.py when it starts
    command = ["python3", "/app/main.py"]
  }
}

output "survey_app_fqdn" {
  value = azurerm_container_group.survey_app.fqdn
}
output "survey_app_public_ip" {
  value = azurerm_container_group.survey_app.ip_address
}

# Ensure you have an output for the SQL server FQDN if you need it elsewhere
# This output assumes you have an azurerm_mssql_server resource named 'sql_server'
# in another .tf file in the same directory (e.g., database.tf).
output "sql_server_fqdn" {
  value = azurerm_mssql_server.sql_server.fully_qualified_domain_name
}
