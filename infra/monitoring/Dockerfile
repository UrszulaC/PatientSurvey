FROM prom/prometheus:v2.47.0

# Copy your Prometheus config into the image
COPY prometheus.yml /etc/prometheus/prometheus.yml

# Expose Prometheus port
EXPOSE 9090

# Run Prometheus with the config file - USE THE CORRECT STORAGE PATH!
CMD ["--config.file=/etc/prometheus/prometheus.yml", "--web.enable-lifecycle", "--storage.tsdb.retention.time=15d"]
