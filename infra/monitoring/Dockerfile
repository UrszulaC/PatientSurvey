FROM prom/prometheus:v2.47.0
COPY prometheus.yml /etc/monitoring/prometheus.yml
EXPOSE 9090
CMD ["/bin/prometheus", "--config.file=/etc/monitoring/prometheus.yml"]
