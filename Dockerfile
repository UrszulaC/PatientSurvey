FROM python:3.9-slim-bullseye

# Install ALL required system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    wget \
    unixodbc \
    unixodbc-dev \
    procps \
    libc6 \
    libgcc1 && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter (v1.6.1)
RUN wget -O /tmp/node_exporter.tar.gz \
    https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz && \
    tar xzf /tmp/node_exporter.tar.gz -C /usr/local/bin/ --strip-components=1 && \
    chmod +x /usr/local/bin/node_exporter && \
    rm /tmp/node_exporter.tar.gz

WORKDIR /app
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Verify ODBC driver is found
RUN odbcinst -j && ldconfig

# Final command
CMD ["sh", "-c", "/usr/local/bin/node_exporter --web.listen-address=0.0.0.0:9100 & cd / && PYTHONPATH=/app python3 -m app.main"]
