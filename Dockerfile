FROM python:3.9-slim-bullseye

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        wget && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter (v1.6.1)
RUN wget https://github.com/prometheus/node_exporter/releases/download/v1.6.1/node_exporter-1.6.1.linux-amd64.tar.gz -O /tmp/node_exporter.tar.gz && \
    tar xzf /tmp/node_exporter.tar.gz -C /usr/local/bin/ --strip-components=1 node_exporter-1.6.1.linux-amd64/node_exporter && \
    rm /tmp/node_exporter.tar.gz && \
    chmod +x /usr/local/bin/node_exporter

# Copy application files
COPY app /app
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Set the working directory to root (since your app runs from /)
WORKDIR /

# Run both services
CMD ["sh", "-c", "/usr/local/bin/node_exporter --web.listen-address=0.0.0.0:9100 & cd / && python3 -m app.main"]
