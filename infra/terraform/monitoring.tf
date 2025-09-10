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
  }

  # Only create if doesn't exist - use data source to check
  count = length(data.azurerm_container_group.existing_prometheus[*]) > 0 ? 0 : 1
}

# Data source to check if Prometheus already exists
data "azurerm_container_group" "existing_prometheus" {
  name                = "prometheus-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
}

output "prometheus_url" {
  value = length(data.azurerm_container_group.existing_prometheus[*]) > 0 ? "http://${data.azurerm_container_group.existing_prometheus.fqdn}:9090" : "http://${azurerm_container_group.prometheus[0].fqdn}:9090"
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

    # Use ONLY secure_environment_variables for sensitive data
    secure_environment_variables = {
      GF_SECURITY_ADMIN_USER     = "admin"
      GF_SECURITY_ADMIN_PASSWORD = var.grafana_password
    }
  }

  # Only create if doesn't exist - use data source to check
  count = length(data.azurerm_container_group.existing_grafana[*]) > 0 ? 0 : 1
}

# Data source to check if Grafana already exists
data "azurerm_container_group" "existing_grafana" {
  name                = "grafana-cg"
  resource_group_name = data.azurerm_resource_group.existing.name
}

output "grafana_url" {
  value = length(data.azurerm_container_group.existing_grafana[*]) > 0 ? "http://${data.azurerm_container_group.existing_grafana.fqdn}:3000" : "http://${azurerm_container_group.grafana[0].fqdn}:3000"
}
