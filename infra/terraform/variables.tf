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

variable "grafana_email" {
  description = "Email address for Grafana alerts"
  type        = string
  sensitive   = true
}

variable "grafana_email_password" {
  description = "App password for Grafana email"
  type        = string
  sensitive   = true
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

variable "client_id" {
  type    = string
  default = ""
}

variable "client_secret" {
  type    = string
  sensitive = true
  default = ""
}

variable "tenant_id" {
  type    = string
  default = ""
}

variable "subscription_id" {
  type    = string
  default = ""
}
