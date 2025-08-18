FROM python:3.9-slim-bullseye

# Install system dependencies including ODBC
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget \
        unixodbc \
        unixodbc-dev \
        odbcinst \
        libodbc1 \
        procps \
        net-tools && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter (container stats only)
RUN wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz && \
    tar xvfz node_exporter-* -C /usr/local/bin/ --strip-components=1 && \
    rm node_exporter-*.tar.gz && \
    chmod +x /usr/local/bin/node_exporter

WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Verify ODBC installation
RUN odbcinst -j && ldconfig

# Expose ports: node_exporter
EXPOSE 9100


# Run both processes: node_exporter in background, app in foreground
CMD sh -c "/usr/local/bin/node_exporter --web.listen-address=0.0.0.0:9100 & exec python3 -m app.main"


