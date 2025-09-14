FROM python:3.9-slim-bullseye

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget curl gnupg unixodbc unixodbc-dev odbcinst libodbc1 procps net-tools apt-transport-https ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter
RUN wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz && \
    tar xvfz node_exporter-* -C /usr/local/bin/ --strip-components=1 && \
    rm node_exporter-*.tar.gz && chmod +x /usr/local/bin/node_exporter

# Install ODBC driver (for your app)
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports: node_exporter + Python app
EXPOSE 9100 8001

# Healthcheck for node_exporter
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD curl -f http://localhost:9100/metrics || exit 1

# Run node_exporter in background and Python app in foreground
CMD ["sh", "-c", "/usr/local/bin/node_exporter --web.listen-address=0.0.0.0:9100 & exec python3 -m app.main"]

