FROM prom/prometheus:v2.47.0

# Copy Prometheus configuration from the same folder
COPY prometheus.yml /etc/prometheus/prometheus.yml

# Expose Prometheus port
EXPOSE 9090

# Base image already runs Prometheus, no need for CMD

