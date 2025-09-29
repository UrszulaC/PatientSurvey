# ===== PERSISTENT STORAGE =====
resource "azurerm_storage_account" "monitoring" {
  name                     = "mypatientsurveymonitor"
  resource_group_name      = var.resource_group_name
  location                 = var.location
  account_tier             = "Standard"
  account_replication_type = "LRS"
}

resource "azurerm_storage_share" "prometheus" {
  name               = "prometheus-data"
  storage_account_id = azurerm_storage_account.monitoring.id
  quota              = 50
}

resource "azurerm_storage_share" "grafana" {
  name               = "grafana-data"
  storage_account_id = azurerm_storage_account.monitoring.id
  quota              = 50
}

# ===== PROMETHEUS =====
resource "azurerm_container_group" "prometheus" {
  name                = "prometheus-cg"
  resource_group_name = var.resource_group_name
  location            = var.location
  os_type             = "Linux"
  restart_policy      = "Always"
  ip_address_type     = "Public"
  dns_name_label      = "prometheus-survey"

  container {
    name   = "prometheus"
    image  = "urszulach/prometheus-custom:${var.prometheus_image_tag}"
    cpu    = "0.5"
    memory = "1.5"
  
    ports {
      port     = 9090
      protocol = "TCP"
    }
  
    volume {
      name                 = "prometheus-data"
      mount_path           = "/prometheus" # This is the correct path for data storage
      read_only            = false # This MUST be false for Prometheus to write its data
      storage_account_name = azurerm_storage_account.monitoring.name
      storage_account_key  = azurerm_storage_account.monitoring.primary_access_key
      share_name           = azurerm_storage_share.prometheus.name
    }
  }

  image_registry_credential {
    server   = "index.docker.io"
    username = var.docker_user
    password = var.docker_password
  }
}

# ===== GRAFANA =====
resource "azurerm_container_group" "grafana" {
  name                = "grafana-cg"
  resource_group_name = var.resource_group_name
  location            = var.location
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
}

# ===== OUTPUTS =====
output "prometheus_url" {
  value = "http://${azurerm_container_group.prometheus.fqdn}:9090"
}

output "grafana_url" {
  value = "http://${azurerm_container_group.grafana.fqdn}:3000"
}

# ===== VARIABLES =====
variable "resource_group_name" {
  description = "Existing resource group name"
  default     = "MyPatientSurveyRG"
}

variable "location" {
  description = "Azure region for resources"
  default     = "uksouth"
}

variable "prometheus_image_tag" {
  description = "Prometheus Docker image tag"
  default     = "latest"
}
