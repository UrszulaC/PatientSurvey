resource "azurerm_container_group" "azure_metrics_exporter" {
  name                = "azure-metrics-exporter"
  location            = var.location
  resource_group_name = var.resource_group_name
  os_type             = "Linux"

  container {
    name   = "exporter"
    image  = "quay.io/giantswarm/azure-exporter:0.5.0"
    cpu    = "0.5"
    memory = "1.0"

    ports {
      port     = 9273
      protocol = "TCP"
    }

    environment_variables = {
      AZURE_SUBSCRIPTION_ID = var.subscription_id
      AZURE_TENANT_ID       = var.tenant_id
      AZURE_CLIENT_ID       = var.client_id
      AZURE_CLIENT_SECRET   = var.client_secret
      # restrict to VM metrics
      AZURE_RESOURCE_TYPE   = "Microsoft.Compute/virtualMachines"
    }
  }

  ip_address_type = "Public"

  dns_name_label = "azure-metrics-exporter-${var.location}"
}

output "azure_exporter_url" {
  description = "Public endpoint for Azure Metrics Exporter"
  value       = "http://${azurerm_container_group.azure_metrics_exporter.ip_address}:9273/metrics"
}
