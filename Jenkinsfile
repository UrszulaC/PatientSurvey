pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG   = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    // DB_HOST will be set dynamically by the Terraform stage
  }

  options {
    // K4: Business value of DevOps (Time, Cost, Quality) - Timeout helps manage pipeline duration
    timeout(time: 25, unit: java.util.concurrent.TimeUnit.MINUTES) // Increased timeout for more installations
  }

  stages {
    stage('Checkout Code') {
      steps {
        // K2: Principles of distributed Source Control (VCS polling is implicit in Jenkins setup)
        checkout scm
      }
    }

    // NEW STAGE: Install Terraform
    stage('Install Terraform') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing Terraform..."

          // --- CRITICAL CLEANUP FIX: Remove problematic azure-cli.list before apt-get update ---
          // This addresses the 'E: Malformed entry 1 in list file /etc/apt/sources.list.d/azure-cli.list' error.
          // It does NOT install Azure CLI; it only cleans up a lingering corrupted file.
          echo "Cleaning up any existing malformed azure-cli.list file..."
          sudo rm -f /etc/apt/sources.list.d/azure-cli.list

          // Install prerequisites
          sudo apt-get update
          // CRITICAL FIX: Use ACCEPT_EULA=Y for msodbcsql17 which might be pulled in as a dependency
          sudo ACCEPT_EULA=Y apt-get install -y software-properties-common wget

          // Add HashiCorp GPG key
          wget -O- https://apt.releases.hashicorp.com/gpg | \\
            gpg --dearmor | \\
            sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null

          // Add HashiCorp Linux repository
          echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \\
            https://apt.releases.hashicorp.com \$(lsb_release -cs) main" | \\
            sudo tee /etc/apt/sources.list.d/hashicorp.list

          // Update and install Terraform
          sudo apt-get update
          sudo apt-get install -y terraform

          echo "Terraform installation complete."
          terraform version
        """
      }
    }

    // NEW STAGE: Install Docker
    stage('Install Docker') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing Docker..."

          // Add Docker's official GPG key:
          sudo apt-get update
          sudo apt-get install -y ca-certificates curl gnupg
          sudo install -m 0755 -d /etc/apt/keyrings

          // CRITICAL FIX: Remove existing key file before adding to prevent "File exists" and "no valid OpenPGP data" errors
          sudo rm -f /etc/apt/keyrings/docker.gpg

          // CRITICAL FIX: Add --batch to gpg for non-interactive execution
          curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --batch -o /etc/apt/keyrings/docker.gpg
          sudo chmod a+r /etc/apt/keyrings/docker.gpg

          // Add the repository to Apt sources:
          echo \\
            "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \\
            \$(. /etc/os-release && echo "\$VERSION_CODENAME") stable" | \\
            sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
          sudo apt-get update

          // Install Docker packages
          sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

          // Add jenkins user to the docker group to run docker commands without sudo
          sudo usermod -aG docker jenkins

          echo "Docker installation complete. Starting Docker service."
          sudo systemctl enable docker
          sudo systemctl start docker

          // IMPORTANT: The Jenkins service restart has been REMOVED from the pipeline.
          // You MUST manually restart Jenkins AFTER this build completes for Docker permissions to take effect.
          echo "Manual Jenkins service restart required for Docker permissions to apply."
        """
      }
    }

    // NEW STAGE: Install Prometheus and Grafana
    stage('Install Monitoring Tools') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing Prometheus..."
          // Download Prometheus (adjust version as needed)
          PROMETHEUS_VERSION="2.53.0" // Check for latest stable version
          wget https://github.com/prometheus/prometheus/releases/download/v\${PROMETHEUS_VERSION}/prometheus-\${PROMETHEUS_VERSION}.linux-amd64.tar.gz -O /tmp/prometheus.tar.gz

          // Extract and move to /usr/local/bin
          tar -xvf /tmp/prometheus.tar.gz -C /tmp/
          sudo mv /tmp/prometheus-\${PROMETHEUS_VERSION}.linux-amd64/prometheus /usr/local/bin/
          sudo mv /tmp/prometheus-\${PROMETHEUS_VERSION}.linux-amd64/promtool /usr/local/bin/

          // Create Prometheus user and directories
          sudo useradd --no-create-home --shell /bin/false prometheus || true // || true to ignore if user exists
          sudo mkdir -p /etc/prometheus /var/lib/prometheus

          // Set ownership
          sudo chown prometheus:prometheus /usr/local/bin/prometheus
          sudo chown prometheus:prometheus /usr/local/bin/promtool
          sudo chown prometheus:prometheus /etc/prometheus
          sudo chown prometheus:prometheus /var/lib/prometheus

          // Basic Prometheus configuration (prometheus.yml)
          sudo tee /etc/prometheus/prometheus.yml > /dev/null <<EOF
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'prometheus'
    static_configs:
      - targets: ['localhost:9090']
  - job_name: 'jenkins'
    static_configs:
      - targets: ['localhost:8080'] // Assuming Jenkins Exporter is running on 8080/metrics
EOF

          // Create systemd service file for Prometheus
          sudo tee /etc/systemd/system/prometheus.service > /dev/null <<EOF
[Unit]
Description=Prometheus
Wants=network-online.target
After=network-online.target

[Service]
User=prometheus
Group=prometheus
Type=simple
ExecStart=/usr/local/bin/prometheus \\
    --config.file /etc/prometheus/prometheus.yml \\
    --storage.tsdb.path /var/lib/prometheus/ \\
    --web.console.templates=/etc/prometheus/consoles \\
    --web.console.libraries=/etc/prometheus/console_libraries

[Install]
WantedBy=multi-user.target
EOF

          // Reload systemd, enable and start Prometheus
          sudo systemctl daemon-reload
          sudo systemctl enable prometheus
          sudo systemctl start prometheus
          echo "Prometheus installation complete."


          echo "Installing Grafana..."
          // Install Grafana (using official APT repository)
          sudo apt-get install -y apt-transport-https software-properties-common wget
          sudo mkdir -p /etc/apt/keyrings/
          // CRITICAL FIX: Remove existing grafana.gpg key file to prevent "File exists" error
          sudo rm -f /etc/apt/keyrings/grafana.gpg
          wget -q -O - https://apt.grafana.com/gpg.key | sudo gpg --dearmor --batch -o /etc/apt/keyrings/grafana.gpg // Added --batch
          echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
          sudo apt-get update
          sudo apt-get install -y grafana

          // Enable and start Grafana
          sudo systemctl daemon-reload
          sudo systemctl enable grafana-server
          sudo systemctl start grafana-server
          echo "Grafana installation complete."
        """
      }
    }

    // Removed: Install Azure CLI stage, as per user's request to manage outside Jenkinsfile.
    // The resource group 'MyPatientSurveyRG' is now manually created.

    stage('Deploy Infrastructure (Terraform)') {
      steps {
        script {
          dir('infra/terraform') { // Correct path for Terraform files
            withCredentials([
              usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER_VAR', passwordVariable: 'DB_PASSWORD_VAR'),
              string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
              string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
              string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
              // Reverted to azure_subscription_id (underscore)
              string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR')
            ])  {
              // <<< THIS IS THE CRUCIAL SH BLOCK THAT MUST BE HERE >>>
              sh """
                # Export Azure credentials for Terraform
                export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
                export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
                export ARM_TENANT_ID="${AZURE_TENANT_ID}"
                export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"

                # Export DB credentials for Terraform - these are sensitive variables for Terraform
                export DB_USER="${DB_USER_VAR}"
                export DB_PASSWORD="${DB_PASSWORD_VAR}"

                # Terraform commands
                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" -backend-config="storage_account_name=mypatientsurveytfstate" -backend-config="container_name=tfstate" -backend-config="key=patient_survey.tfstate"
                terraform plan -out=tfplan.out -var="db_user=\${DB_USER}" -var="db_password=\${DB_PASSWORD}"
                terraform apply -auto-approve tfplan.out
              """
              def sqlServerFqdn = sh(script: "terraform output -raw sql_server_fqdn", returnStdout: true).trim()
              env.DB_HOST = sqlServerFqdn
              echo "Database Host FQDN: ${env.DB_HOST}"
            }
          }
        }
      }
    }

    stage('Create .env File') {
      steps {
        // Operate from the workspace root to correctly create package __init__.py files
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            echo "DB_HOST=${DB_HOST}" > app/.env
            echo "DB_USER=$DB_USER" >> app/.env
            echo "DB_PASSWORD=$DB_PASSWORD" >> app/.env
            echo "DB_NAME=${DB_NAME}" >> app/.env

            // NEW: Create __init__.py files to make 'app' and 'utils' discoverable Python packages
            echo "Creating __init__.py files..."
            touch app/__init__.py // Makes 'app' a package
            touch app/utils/__init__.py // Makes 'utils' a subpackage within 'app'
            echo "__init__.py files created."
          '''
        }
      }
    }

    stage('Install Dependencies') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing ODBC Driver for SQL Server..."

          export DEBIAN_FRONTEND=noninteractive
          export TZ=Etc/UTC

          // 1. Install prerequisites for adding Microsoft repositories
          sudo apt-get update
          // CRITICAL FIX: Install python3-pip and python3-venv here
          sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring python3-pip python3-venv

          // CRITICAL FIX: Remove existing microsoft-prod.gpg key file to prevent "File exists" error
          sudo rm -f /usr/share/keyrings/microsoft-prod.gpg
          // 2. Import the Microsoft GPG key
          curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor --batch -o /usr/share/keyrings/microsoft-prod.gpg // Added --batch

          // 3. Add the Microsoft SQL Server repository (adjust for your Ubuntu version if not 22.04)
          echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \\
          | sudo tee /etc/apt/sources.list.d/mssql-release.list

          // 4. Update apt-get cache and install the ODBC driver
          sudo apt-get update
          // CRITICAL FIX: Pipe 'yes' directly to the install command to accept EULA
          yes | sudo apt-get install -y msodbcsql17 unixodbc-dev

          echo "ODBC Driver installation complete."

          // Now, proceed with Python dependencies
          python3 --version
          pip3 install --upgrade pip
          pip install -r app/requirements.txt // Correct path to requirements.txt
        """
      }
    }

    stage('Security Scan') {
      steps {
        dir('app') { // Assuming app files are in 'app/' directory for Bandit scan context
          // K5: Modern security tools (Bandit, Pip-audit)
          // S9: Application of cloud security tools into automated pipeline
          sh """
            #!/usr/bin/env bash
            set -ex // Added -x for debugging output, and -e for exiting on error

            echo "Installing security tools (bandit, pip-audit)..."
            timeout 5m python3 -m pip install --user bandit pip-audit
            echo "Security tools installed."

            export PATH=$HOME/.local/bin:$PATH
            echo "PATH updated: $PATH"

            echo "Running static code analysis with Bandit..."
            bandit -r . -lll // Scan current directory (app/)
            echo "Bandit scan complete."

            echo "Running dependency audit with pip-audit..."
            timeout 5m pip-audit -r requirements.txt --verbose // requirements.txt is in app/
            echo "pip-audit complete."
          """
        }
      }
    }

    stage('Run Tests') {
      steps {
        // K14: Test Driven Development and Test Pyramid (Unit testing)
        // S14: Write tests and follow TDD discipline
        // S17: Code in a general-purpose programming language (Python tests)
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            export PATH=$HOME/.local/bin:$PATH
            export DB_USER=$DB_USER
            export DB_PASSWORD=$DB_PASSWORD
            // Ensure the workspace root is in PYTHONPATH for module discovery
            export PYTHONPATH=.:$PYTHONPATH
            echo "PYTHONPATH updated: $PYTHONPATH"

            // Ensure tests/ is a Python package for discovery (already handled by touch app/tests/__init__.py if tests are inside app)
            // If tests/ is at the root, ensure tests/__init__.py is created at root
            mkdir -p tests // Ensure tests directory exists at root
            touch tests/__init__.py // Make 'tests' a package

            // Discover tests in the 'tests' directory at the workspace root
            python3 -m xmlrunner discover -s tests -o test-results
          '''
        }
      }
    }

    stage('Build Docker Image') {
      steps {
        script {
          // The Dockerfile is at the repository root, so build from the workspace root.
          // Ensure your Dockerfile is named 'Dockerfile' (with a capital D) at the root.
          echo "Building Docker image ${IMAGE_TAG}..."
          docker.build(IMAGE_TAG, '.') // Explicitly set build context to current directory (repo root)
          echo "Docker image built successfully."
        }
      }
    }

    stage('Container Scan') {
      steps {
        // K5: Modern security tools (Trivy)
        // S9: Application of cloud security tools into automated pipeline
        sh """
          #!/usr/bin/env bash
          set -ex

          echo "Installing Trivy..."
          if ! command -v trivy &>/dev/null; then
            timeout 5m curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \\
              | bash -s -- -b "\$HOME/.local/bin"
          fi
          echo "Trivy installed."

          export PATH="\$HOME/.local/bin:\$PATH"
          echo "PATH updated for Trivy: \$PATH"

          echo "Running container scan with Trivy..."
          timeout 10m trivy image --severity HIGH,CRITICAL ${IMAGE_TAG}
          echo "Trivy scan complete."
        """
      }
    }

    stage('Push Docker Image') {
      steps {
        script {
          // K1: Continuous Integration (Build artifacts)
          // K15: Continuous Integration/Delivery/Deployment principles
          echo "Pushing Docker image ${IMAGE_TAG} to Docker Hub..."
          docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
            docker.image(IMAGE_TAG).push()
            docker.image(IMAGE_TAG).push('latest') // Optional: push as latest for easier pulling
          }
          echo "Docker image pushed successfully."
        }
      }
    }

    stage('Deploy Application (Azure Container Instances)') {
      steps {
        script {
          withCredentials([
            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
            string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
            // Reverted to azure_subscription_id (underscore)
            string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR')
          ]) {
            // K15: Continuous Delivery/Deployment (Automated deployment)
            // K8: Immutable infrastructure (Deploying container image)
            // S5: Deploy immutable infrastructure
            // S12: Automate tasks (Azure CLI deployment)
            // Note: This deploys the console app in a container. For an API-based app,
            // the application code itself would need refactoring to expose an API.
            sh """
              echo "Logging into Azure..."
              az login --service-principal -u "${AZURE_CLIENT_ID}" -p "${AZURE_CLIENT_SECRET}" --tenant "${AZURE_TENANT_ID}"
              az account set --subscription "${AZURE_SUBSCRIPTION_ID_VAR}"

              RESOURCE_GROUP_NAME="MyPatientSurveyRG" // Assuming this RG is managed by Terraform
              ACI_NAME="patientsurvey-app-${env.BUILD_NUMBER}"
              ACI_LOCATION="uksouth" // Adjust as per your Azure region

              echo "Deploying Docker image ${IMAGE_TAG} to Azure Container Instances..."

              az container create \\
                --resource-group \$RESOURCE_GROUP_NAME \\
                --name \$ACI_NAME \\
                --image ${IMAGE_TAG} \\
                --os-type Linux \\
                --cpu 1 \\
                --memory 1.5 \\
                --restart-policy Always \\
                --location \$ACI_LOCATION \\
                --environment-variables DB_HOST=${DB_HOST} DB_USER=${DB_USER} DB_PASSWORD=${DB_PASSWORD} DB_NAME=${DB_NAME} \\
                --no-wait // Do not wait for deployment to complete to speed up pipeline

              echo "Azure Container Instance deployment initiated. Check Azure portal for status."

              echo "Logging out of Azure..."
              az logout
            """
          }
        }
      }
    }
  }

  post {
    always {
      // K1: Continuous Integration (Ensuring all tests pass)
      junit 'test-results/*.xml' // Corrected path for JUnit reports
      cleanWs()
    }
  }
}
