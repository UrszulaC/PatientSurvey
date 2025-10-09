# Python 3.9 slim image
FROM python:3.9-slim-bullseye

# Set non-interactive environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies and ODBC prerequisites
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 unixodbc unixodbc-dev odbcinst libodbc1 \
        apt-transport-https ca-certificates gcc libffi-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

# ✅ Securely add Microsoft package repository (keyring method)
RUN mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg && \
    echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" \
        > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app
ENV PYTHONPATH=/app

# Copy app source code
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy HTML templates
COPY templates/ ./templates/

# Expose Flask app port
EXPOSE 8001

# Healthcheck for Flask application
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Start Flask application
CMD ["python", "-m", "app.main"]
