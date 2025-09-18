# Python 3.9 base image
FROM python:3.9-slim-bullseye

# System dependencies for ODBC
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        curl gnupg2 unixodbc unixodbc-dev odbcinst libodbc1 \
        apt-transport-https ca-certificates gcc libffi-dev python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Microsoft ODBC Driver 17 for SQL Server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - && \
    curl https://packages.microsoft.com/config/debian/11/prod.list > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && \
    ACCEPT_EULA=Y apt-get install -y msodbcsql17 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app
ENV PYTHONPATH=/app

# Copy app source
COPY . .
COPY templates/ ./templates/

# Install Python dependencies (make sure Flask is in requirements.txt!)
RUN pip install --no-cache-dir -r requirements.txt

# Expose Flask app port
EXPOSE 8001

# Healthcheck for Flask application
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Start Flask application
CMD ["python", "-m", "app.main"]
