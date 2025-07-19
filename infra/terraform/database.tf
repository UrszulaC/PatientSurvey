# Existing providers and resource group data
# ... (ensure these are present and correct in your main.tf) ...

resource "random_integer" "sql_suffix" {
  min = 1000
  max = 9999
}

resource "azurerm_mssql_server" "sql_server" { # CHANGED HERE
  name                         = "patientsurveysql${random_integer.sql_suffix.result}" # Unique name
  resource_group_name          = data.azurerm_resource_group.existing.name
  location                     = data.azurerm_resource_group.existing.location
  version                      = "12.0" # Use "12.0" for Azure SQL Database, or "17.0" for Azure SQL Managed Instance. "12.0" is safer for App Service.
  administrator_login          = var.db_user
  administrator_login_password = var.db_password # Get from Jenkins creds later
  minimum_tls_version          = "1.2" # K16: Good security practice

  # K16: Security - Enable public network access for ACI direct connection.
  # WARNING: In production, use Private Link or VNet integration for ACI.
  # For your EPA, this simplifies connectivity and is acceptable if explained.
  public_network_access_enabled = true
}

resource "azurerm_mssql_database" "sql_database" { 
  name                 = "patient_survey_db" # The DB_NAME your app uses
  resource_group_name  = data.azurerm_resource_group.existing.name
  location             = data.azurerm_resource_group.existing.location
  server_name          = azurerm_mssql_server.sql_server.name # ALSO UPDATE REFERENCE
  collation            = "SQL_Latin1_General_CP1_CI_AS"
  max_size_gb          = 2 # Adjust as needed
  sku_name             = "Basic" # Adjust as needed for performance/cost

  # K16: Encryption at rest (Transparent Data Encryption)
  transparent_data_encryption_enabled = true
}

# K16: Firewall rule for Azure services to access the SQL Server
# This is typically needed for Azure services like ACI or App Service
# to connect when not using Private Endpoints.
resource "azurerm_mssql_firewall_rule" "allow_azure_services" { # CHANGED HERE
  name                = "AllowAzureServices"
  resource_group_name = data.azurerm_resource_group.existing.name
  server_name         = azurerm_mssql_server.sql_server.name # ALSO UPDATE REFERENCE
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"
}

# Output the SQL Server FQDN for your application to use
output "sql_server_fqdn" {
  value       = azurerm_mssql_server.sql_server.fqdn # ALSO UPDATE REFERENCE
  description = "The FQDN of the Azure SQL Server."
}
