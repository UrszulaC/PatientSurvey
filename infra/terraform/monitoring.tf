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

    # Mount configuration via environment variable or volume if needed
  }

  # CRITICAL: Prevent recreation of DNS and IP properties
  lifecycle {
    ignore_changes = [
      dns_name_label,
      ip_address_type,
      fqdn
    ]
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

    environment_variables = {
      GF_SECURITY_ADMIN_USER     = "admin"
      GF_SECURITY_ADMIN_PASSWORD = var.grafana_password
    }

    # Secure sensitive environment variables
    secure_environment_variables = {
      GF_SECURITY_ADMIN_PASSWORD = var.grafana_password
    }
  }

  # CRITICAL: Prevent recreation of DNS and IP properties
  lifecycle {
    ignore_changes = [
      dns_name_label,
      ip_address_type,
      fqdn
    ]
  }
}

output "grafana_url" {
  value = "http://${azurerm_container_group.grafana.fqdn}:3000"
}
