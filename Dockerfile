FROM python:3.9-slim-bullseye

WORKDIR /app

# Install system dependencies with cleanup
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl wget procps && \
    wget https://github.com/prometheus/node_exporter/releases/download/v1.3.1/node_exporter-1.3.1.linux-amd64.tar.gz && \
    tar xvfz node_exporter-*.tar.gz && \
    mv node_exporter-*/node_exporter /usr/local/bin/ && \
    chmod +x /usr/local/bin/node_exporter && \
    rm -rf node_exporter-* && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

COPY app/ .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000 9100

# Create robust startup script
RUN echo '#!/bin/sh\n\
# Start node_exporter with full debugging\n\
/usr/local/bin/node_exporter --web.listen-address=:9100 --log.level=debug > /proc/1/fd/1 2>&1 &\n\
# Start main application\n\
exec python3 /app/main.py' > /start.sh && \
    chmod +x /start.sh

# Healthcheck only for main app
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/start.sh"]
