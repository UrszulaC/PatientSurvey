# Existing providers and resource group data
# ... (ensure these are present and correct in your main.tf) ...

resource "random_integer" "sql_suffix" {
  min = 1000
  max = 9999
}
resource "azurerm_mssql_server" "sql_server" {
  name                         = "patientsurveysql${random_integer.sql_suffix.result}" # Unique name
  resource_group_name          = data.azurerm_resource_group.existing.name
  location                     = data.azurerm_resource_group.existing.location
  version                      = "12.0" # Use "12.0" for Azure SQL Database, or "17.0" for Azure SQL Managed Instance. "12.0" is safer for App Service.
  administrator_login          = var.db_user
  administrator_login_password = var.db_password
  minimum_tls_version          = "1.2" # K16: Good security practice

  public_network_access_enabled = true
}

resource "azurerm_mssql_database" "sql_database" {
  name                 = "patient_survey_db" # The DB_NAME your app uses
  server_id            = azurerm_mssql_server.sql_server.id # <--- NEW: Use server_id
  collation            = "SQL_Latin1_General_CP1_CI_AS"
  max_size_gb          = 2 # Adjust as needed
  sku_name             = "Basic" 

  # K16: Encryption at rest (Transparent Data Encryption)
  transparent_data_encryption_enabled = true
}

resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name                = "AllowAzureServices"
  server_id           = azurerm_mssql_server.sql_server.id # <--- NEW: Use server_id
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"
}

# Output the SQL Server FQDN for your application to use
output "sql_server_fqdn" {
  value       = azurerm_mssql_server.sql_server.fully_qualified_domain_name # <--- NEW: Use fully_qualified_domain_name
  description = "The FQDN of the Azure SQL Server."
}

