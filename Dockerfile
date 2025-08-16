FROM python:3.9-slim-bullseye

WORKDIR /app

# Install minimal requirements + supervisor
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        supervisor \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Install node_exporter directly (no extraction needed)
RUN curl -L https://github.com/prometheus/node_exporter/releases/download/v1.3.1/node_exporter-1.3.1.linux-amd64.tar.gz | \
    tar xvz -C /usr/local/bin/ --strip-components=1 node_exporter-1.3.1.linux-amd64/node_exporter && \
    chmod +x /usr/local/bin/node_exporter

COPY app/ .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Configure supervisor
RUN echo '[supervisord]\n\
nodaemon=true\n\
[program:node_exporter]\n\
command=/usr/local/bin/node_exporter --web.listen-address=:9100\n\
autorestart=true\n\
[program:app]\n\
command=python3 /app/main.py\n\
autorestart=true\n' > /etc/supervisor/conf.d/supervisord.conf

EXPOSE 9100

# Healthcheck only for main app
HEALTHCHECK --interval=30s --timeout=5s \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["/usr/bin/supervisord"]
