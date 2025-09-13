variable "db_user" {
  description = "Database username for the survey app"
  type        = string
}

variable "db_password" {
  description = "Database password for the survey app"
  type        = string
  sensitive   = true
}
variable "grafana_password" {
  type        = string
  description = "Admin password for Grafana"
  sensitive   = true
}
variable "subscription_id" {
  type        = string
  description = "Azure subscription ID"
}

variable "client_id" {
  type        = string
  description = "Azure service principal client ID"
}

variable "client_secret" {
  type        = string
  sensitive   = true
  description = "Azure service principal client secret"
}

variable "tenant_id" {
  type        = string
  description = "Azure tenant ID"
}

variable "docker_user" {
  description = "Docker Hub username for private images"
  type        = string
}

variable "docker_password" {
  description = "Docker Hub password for private images"
  type        = string
  sensitive   = true
}

