FROM python:3.9-slim-bullseye

WORKDIR /app

# Install minimal requirements
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter (v1.6.1)
RUN wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz -O /tmp/node_exporter.tar.gz && \
    tar xzf /tmp/node_exporter.tar.gz -C /usr/local/bin/ --strip-components=1 node_exporter-1.6.1.linux-amd64/node_exporter && \
    rm /tmp/node_exporter.tar.gz && \
    chmod +x /usr/local/bin/node_exporter

COPY app/ .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Run both services (node_exporter in background, app in foreground)
EXPOSE 9100

CMD ["sh", "-c", "/usr/local/bin/node_exporter --web.listen-address=0.0.0.0:9100 & python3 /app/main.py"]
