# Use an official Python runtime as a parent image
# CRITICAL FIX: Changed base image from buster (Debian 10) to bullseye (Debian 11)
# Buster repositories are no longer actively maintained at the default URLs.
FROM python:3.9-slim-bullseye

# Set the working directory in the container
# All subsequent commands will be run relative to this directory.
WORKDIR /app

# Install ODBC Driver for SQL Server
# Based on instructions for Debian 11 (Bullseye)
# This section ensures the ODBC driver is installed inside the Docker image
RUN apt-get update && apt-get install -y --no-install-recommends \
    apt-transport-https \
    curl \
    gnupg \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/11/prod bullseye main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
    msodbcsql17 \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

# CRITICAL FIX: Copy the *contents* of the local 'app' directory into the WORKDIR (/app)
# This will place main.py, config.py, utils/, etc., directly under /app
COPY app/ .

# Install any needed Python packages specified in requirements.txt
# Assuming requirements.txt is located within the 'app/' directory in your repo,
# and will be copied to /app by the previous COPY command.
RUN pip install --no-cache-dir -r requirements.txt

# Expose port 8000 for Prometheus metrics
EXPOSE 8000

# Keep the container running indefinitely for debugging
# This allows you to exec into the container even if the Python app crashes
CMD ["tail", "-f", "/dev/null"]

# Original CMD (commented out for debugging):
# CMD ["python3", "/app/main.py"]
