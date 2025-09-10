# Get existing resource group
data "azurerm_resource_group" "existing" {
  name = "MyPatientSurveyRG"
}

# ===== PROMETHEUS =====
resource "azurerm_container_group" "prometheus" {
  name                = "prometheus-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "prometheus-survey"

  container {
    name   = "prometheus"
    image  = "prom/prometheus:v2.47.0"
    cpu    = "0.5"
    memory = "1.5"

    ports {
      port     = 9090
      protocol = "TCP"
    }

    volume {
      name                 = "prometheus-data"
      mount_path           = "/prometheus"
      read_only            = false
      storage_account_name = azurerm_storage_account.monitoring.name
      storage_account_key  = azurerm_storage_account.monitoring.primary_access_key
      share_name           = azurerm_storage_share.prometheus.name
    }
  }

  lifecycle {
    ignore_changes = [
      dns_name_label,
      ip_address_type
    ]
  }
}

# ===== GRAFANA =====
resource "azurerm_container_group" "grafana" {
  name                = "grafana-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
  location            = data.azurerm_resource_group.existing.location
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "grafana-survey"

  container {
    name   = "grafana"
    image  = "grafana/grafana:9.5.6"
    cpu    = "0.5"
    memory = "1.5"

    ports {
      port     = 3000
      protocol = "TCP"
    }

    volume {
      name                 = "grafana-data"
      mount_path           = "/var/lib/grafana"
      read_only            = false
      storage_account_name = azurerm_storage_account.monitoring.name
      storage_account_key  = azurerm_storage_account.monitoring.primary_access_key
      share_name           = azurerm_storage_share.grafana.name
    }

    secure_environment_variables = {
      GF_SECURITY_ADMIN_USER     = "admin"
      GF_SECURITY_ADMIN_PASSWORD = var.grafana_password
    }
  }

  lifecycle {
    ignore_changes = [
      dns_name_label,
      ip_address_type
    ]
  }
}

# ===== PERSISTENT STORAGE =====
resource "azurerm_storage_account" "monitoring" {
  name                     = "monitoring${replace(substr(uuid(), 0, 8), "-", "")}"
  resource_group_name      = data.azurerm_resource_group.existing.name
  location                 = data.azurerm_resource_group.existing.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_share" "prometheus" {
  name                 = "prometheus-data"
  storage_account_name = azurerm_storage_account.monitoring.name
  quota                = 50
}

resource "azurerm_storage_share" "grafana" {
  name                 = "grafana-data"
  storage_account_name = azurerm_storage_account.monitoring.name
  quota                = 50
}

output "prometheus_url" {
  value = "http://${azurerm_container_group.prometheus.fqdn}:9090"
}

output "grafana_url" {
  value = "http://${azurerm_container_group.grafana.fqdn}:3000"
}
