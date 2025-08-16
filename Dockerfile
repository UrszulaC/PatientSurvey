FROM python:3.9-slim-bullseye

# Setting the working directory
WORKDIR /app

# Install system dependencies including node-exporter
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    curl \
    gnupg \
    wget \
    procps \  # Added for debugging tools (ps)
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql17 \
    unixodbc-dev \
    && wget https://github.com/prometheus/node_exporter/releases/download/v1.3.1/node_exporter-1.3.1.linux-amd64.tar.gz \
    && tar xvfz node_exporter-* \
    && mv node_exporter-*/node_exporter /usr/local/bin/ \
    && chmod +x /usr/local/bin/node_exporter \
    && rm -rf node_exporter-* \
    && rm -rf /var/lib/apt/lists/*

# Copy application files
COPY app/ .
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose ports
EXPOSE 8000
EXPOSE 9100

# Create a more robust startup script
RUN echo '#!/bin/sh\n\
# Start node_exporter and log to stdout\n\
/usr/local/bin/node_exporter --web.listen-address=:9100 > /proc/1/fd/1 2>&1 &\n\
# Start main application\n\
exec python3 /app/main.py' > /start.sh && chmod +x /start.sh

# Health check (more resilient)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD sh -c "curl -f http://localhost:8000/health || exit 1"

# Start services using the script
CMD ["/start.sh"]
