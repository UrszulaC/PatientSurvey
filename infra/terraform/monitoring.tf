# ===== Prometheus Container =====
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

    # Volume mount for Prometheus configuration (optional)
    volume {
      name      = "prometheus-config"
      mount_path = "/etc/prometheus"
      read_only = true
      empty_dir = true
    }
  }

  # CRITICAL: Prevent any changes to existing resources
  lifecycle {
    ignore_changes = all
  }
}

output "prometheus_url" {
  value = "http://${azurerm_container_group.prometheus.fqdn}:9090"
}

# ===== Grafana Container =====
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

    # Use secure environment variables for sensitive data
    secure_environment_variables = {
      GF_SECURITY_ADMIN_USER     = "admin"
      GF_SECURITY_ADMIN_PASSWORD = var.grafana_password
    }

    # Volume mount for Grafana data persistence (optional)
    volume {
      name      = "grafana-storage"
      mount_path = "/var/lib/grafana"
      read_only = false
      empty_dir = true
    }
  }

  # CRITICAL: Prevent any changes to existing resources
  lifecycle {
    ignore_changes = all
  }
}

output "grafana_url" {
  value = "http://${azurerm_container_group.grafana.fqdn}:3000"
}

# ===== Optional: Data sources if you need to reference existing resources =====
data "azurerm_container_group" "existing_prometheus" {
  name                = "prometheus-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
}

data "azurerm_container_group" "existing_grafana" {
  name                = "grafana-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
}
