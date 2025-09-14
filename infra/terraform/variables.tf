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


variable "docker_user" {
  description = "Docker Hub username for private images"
  type        = string
}

variable "docker_password" {
  description = "Docker Hub password for private images"
  type        = string
  sensitive   = true
}
variable "prometheus_image_tag" {
  description = "Prometheus Docker image tag"
  default     = "latest"
}

