# Existing providers and resource group data

resource "random_integer" "sql_suffix" {
  min = 1000
  max = 9999
}
resource "azurerm_mssql_server" "sql_server" {
  name                         = "patientsurveysql"
  resource_group_name          = data.azurerm_resource_group.existing.name
  location                     = data.azurerm_resource_group.existing.location
  version                      = "12.0" 
  administrator_login          = var.db_user
  administrator_login_password = var.db_password
  minimum_tls_version          = "1.2" # K16: Good security practice
  public_network_access_enabled = true
}

resource "azurerm_mssql_database" "sql_database" {
  name                 = "patient_survey_db" 
  server_id            = azurerm_mssql_server.sql_server.id 
  collation            = "SQL_Latin1_General_CP1_CI_AS"
  max_size_gb          = 2 # Adjust as needed
  sku_name             = "Basic" 

  # K16: Encryption at rest (Transparent Data Encryption)
  transparent_data_encryption_enabled = true
}

resource "azurerm_mssql_firewall_rule" "allow_azure_services" {
  name                = "AllowAzureServices"
  server_id           = azurerm_mssql_server.sql_server.id 
  start_ip_address    = "0.0.0.0"
  end_ip_address      = "0.0.0.0"
}
resource "azurerm_network_security_group" "monitoring_nsg" {
  name                = "monitoring-nsg"
  location            = data.azurerm_resource_group.existing.location
  resource_group_name = data.azurerm_resource_group.existing.name

  security_rule {
    name                       = "allow-grafana"
    priority                   = 100
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "3000"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }

  security_rule {
    name                       = "allow-prometheus"
    priority                   = 110
    direction                  = "Inbound"
    access                     = "Allow"
    protocol                   = "Tcp"
    source_port_range          = "*"
    destination_port_range     = "9090"
    source_address_prefix      = "*"
    destination_address_prefix = "*"
  }
}
# Output the SQL Server FQDN for your application to use
output "sql_server_fqdn" {
  value       = azurerm_mssql_server.sql_server.fully_qualified_domain_name
  description = "The FQDN of the Azure SQL Server."
}

