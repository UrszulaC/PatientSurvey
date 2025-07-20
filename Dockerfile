# Use an official Python runtime as a parent image
FROM python:3.9-slim-buster

# Set the working directory in the container
WORKDIR /app

# Install ODBC Driver for SQL Server
# Based on instructions for Ubuntu 20.04 (Buster is Debian-based, similar apt structure)
# This section ensures the ODBC driver is installed inside the Docker image
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    curl \
    gnupg \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/10/prod buster main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql17 \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed Python packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000 for Prometheus metrics
EXPOSE 8000

# CRITICAL CHANGE: Keep the container running indefinitely for debugging
# This allows you to exec into the container even if the Python app crashes
CMD ["tail", "-f", "/dev/null"]

# Original CMD (commented out for debugging):
# CMD ["python3", "/app/main.py"]
