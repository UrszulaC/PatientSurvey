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

