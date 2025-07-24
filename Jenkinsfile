pipeline {
    agent any

    environment {
        DB_NAME = 'patient_survey_db'
        IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    }

    options {
        timeout(time: 25, unit: 'MINUTES')
    }

    stages {
        stage('Clean Environment') {
          steps {
            sh '''
              #!/usr/bin/env bash
              set -e
    
              echo "Starting environment cleanup..."
    
              echo "Checking for and removing dpkg/apt locks..."
              for lock_file in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock /var/lib/apt/lists/lock; do
                if [ -f "$lock_file" ]; then
                  echo "Found lock file: $lock_file"
                  # Find process holding the lock and kill it
                  PIDS=$(sudo fuser -k "$lock_file" 2>/dev/null || true) # Use || true to prevent script exit if fuser fails/finds nothing
                  if [ -n "$PIDS" ]; then
                    echo "Killed processes holding $lock_file: $PIDS"
                  fi
                  sudo rm -f "$lock_file"
                fi
              done
    
              # Ensure dpkg is configured correctly after potential crashes
              sudo dpkg --configure -a || true # Use || true to prevent script exit if dpkg --configure -a fails due to transient issues
              echo "Environment cleanup complete."
            '''
          }
        }
        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        stage('Install Terraform') {
            steps {
                sh '''
                    #!/usr/bin/env bash
                    set -e

                    echo "Installing Terraform..."
                    sudo rm -f /var/lib/apt/lists/lock
                    sudo rm -f /var/cache/apt/archives/lock
                    sudo rm -f /var/lib/dpkg/lock-frontend
                    sudo dpkg --configure -a

                    echo "Cleaning up any existing malformed azure-cli.list file..."
                    sudo rm -f /etc/apt/sources.list.d/azure-cli.list

                    sudo apt-get update
                    sudo ACCEPT_EULA=Y apt-get install -y software-properties-common wget

                    wget -O- https://apt.releases.hashicorp.com/gpg | \\
                        gpg --dearmor | \\
                        sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null

                    echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \\
                        https://apt.releases.hashicorp.com \$(lsb_release -cs) main" | \\
                        sudo tee /etc/apt/sources.list.d/hashicorp.list

                    sudo apt-get update
                    sudo apt-get install -y terraform

                    echo "Terraform installation complete."
                    terraform version
                '''
            }
        }
        
        stage('Install Docker') {
            steps {
                sh '''
                    #!/usr/bin/env bash
                    set -e

                    echo "Installing Docker..."
                    sudo rm -f /var/lib/apt/lists/lock
                    sudo rm -f /var/cache/apt/archives/lock
                    sudo rm -f /var/lib/dpkg/lock-frontend
                    sudo dpkg --configure -a

                    sudo apt-get update
                    sudo apt-get install -y ca-certificates curl gnupg
                    sudo install -m 0755 -d /etc/apt/keyrings

                    sudo rm -f /etc/apt/keyrings/docker.gpg
                    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --batch -o /etc/apt/keyrings/docker.gpg
                    sudo chmod a+r /etc/apt/keyrings/docker.gpg

                    echo \\
                        "deb [arch=\$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \\
                        \$(. /etc/os-release && echo "\$VERSION_CODENAME") stable" | \\
                        sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                    sudo apt-get update

                    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
                    sudo usermod -aG docker jenkins

                    echo "Docker installation complete. Starting Docker service."
                    sudo systemctl enable docker
                    sudo systemctl start docker
                '''
            }
        }
        stage('Install Azure CLI') {
            steps {
                sh '''
                    # Install Azure CLI
                    echo "Installing Azure CLI..."
                    curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
                    echo "Azure CLI installed successfully."
                    az --version
                '''
            }
        }
    //     stage('Install Monitoring Tools') {
    //       steps {
    //         sh """
    //           #!/usr/bin/env bash
    //           set -e
    
    //           echo "Installing Prometheus..."
    //           # Download Prometheus (adjust version as needed)
    //           PROMETHEUS_VERSION="2.53.0" # Check for latest stable version
    //           wget https://github.com/prometheus/prometheus/releases/download/v\${PROMETHEUS_VERSION}/prometheus-\${PROMETHEUS_VERSION}.linux-amd64.tar.gz -O /tmp/prometheus.tar.gz
    
    //           # Extract and move to /usr/local/bin
    //           tar -xvf /tmp/prometheus.tar.gz -C /tmp/
    //           sudo mv /tmp/prometheus-\${PROMETHEUS_VERSION}.linux-amd64/prometheus /usr/local/bin/
    //           sudo mv /tmp/prometheus-\${PROMETHEUS_VERSION}.linux-amd64/promtool /usr/local/bin/
    
    //           # Create Prometheus user and directories
    //           sudo useradd --no-create-home --shell /bin/false prometheus || true # || true to ignore if user exists
    //           sudo mkdir -p /etc/prometheus /var/lib/prometheus
    
    //           # Set ownership
    //           sudo chown prometheus:prometheus /usr/local/bin/prometheus
    //           sudo chown prometheus:prometheus /usr/local/bin/promtool
    //           sudo chown prometheus:prometheus /etc/prometheus
    //           sudo chown prometheus:prometheus /var/lib/prometheus
    
    //           # Basic Prometheus configuration (prometheus.yml)
    //           sudo tee /etc/prometheus/prometheus.yml > /dev/null <<EOF
    // global:
    //   scrape_interval: 15s
    
    // scrape_configs:
    //   - job_name: 'prometheus'
    //     static_configs:
    //       - targets: ['localhost:9090']
    //   - job_name: 'jenkins'
    //     static_configs:
    //       - targets: ['localhost:8080'] # Assuming Jenkins Exporter is running on 8080/metrics
    // EOF
    
    //           # Create systemd service file for Prometheus
    //           sudo tee /etc/systemd/system/prometheus.service > /dev/null <<EOF
    // [Unit]
    // Description=Prometheus
    // Wants=network-online.target
    // After=network-online.target
    
    // [Service]
    // User=prometheus
    // Group=prometheus
    // Type=simple
    // ExecStart=/usr/local/bin/prometheus \\
    //     --config.file /etc/prometheus/prometheus.yml \\
    //     --storage.tsdb.path /var/lib/prometheus/ \\
    //     --web.console.templates=/etc/prometheus/consoles \\
    //     --web.console.libraries=/etc/prometheus/console_libraries
    
    // [Install]
    // WantedBy=multi-user.target
    // EOF
    
    //           # Reload systemd, enable and start Prometheus
    //           sudo systemctl daemon-reload
    //           sudo systemctl enable prometheus
    //           sudo systemctl start prometheus
    //           echo "Prometheus installation complete."
    
    
    //           echo "Installing Grafana..."
    //           # Install Grafana (using official APT repository)
    //           sudo apt-get install -y apt-transport-https software-properties-common wget
    //           sudo mkdir -p /etc/apt/keyrings/
    //           # CRITICAL FIX: Remove existing grafana.gpg key file to prevent "File exists" error
    //           sudo rm -f /etc/apt/keyrings/grafana.gpg
    //           wget -q -O - https://apt.grafana.com/gpg.key | sudo gpg --dearmor --batch -o /etc/apt/keyrings/grafana.gpg # Added --batch
    //           echo "deb [signed-by=/etc/apt/keyrings/grafana.gpg] https://apt.grafana.com stable main" | sudo tee /etc/apt/sources.list.d/grafana.list
    //           sudo apt-get update
    //           sudo apt-get install -y grafana
    
    //           # Enable and start Grafana
    //           sudo systemctl daemon-reload
    //           sudo systemctl enable grafana-server
    //           sudo systemctl start grafana-server
    //           echo "Grafana installation complete."
    //         """
    //       }
    //     }
        
        stage('Deploy Monitoring Stack') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID'),
                        string(credentialsId: 'GRAFANA_PASSWORD', variable: 'GRAFANA_PASSWORD')
                    ]) {
                        sh '''
                        #!/bin/bash
                        set -e
        
                        echo "Logging into Azure..."
                        az login --service-principal -u $ARM_CLIENT_ID -p $ARM_CLIENT_SECRET --tenant $ARM_TENANT_ID
                        az account set --subscription $ARM_SUBSCRIPTION_ID
        
                        # Generate unique names
                        PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                        GRAFANA_NAME="grafana-${BUILD_NUMBER}"
        
                        # Deploy Prometheus (ephemeral storage)
                        az container create \
                            --resource-group MyPatientSurveyRG \
                            --name ${PROMETHEUS_NAME} \
                            --image prom/prometheus \
                            --os-type Linux \
                            --cpu 1 \
                            --memory 2   
                            --ports 9090 \
                            --ip-address Public \
                            --location uksouth \
                            --command-line "--config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.console.templates=/usr/share/prometheus/consoles --web.console.libraries=/usr/share/prometheus/console_libraries" \
                            --no-wait
        
                        // Deploy Grafana (ephemeral storage)
                        az container create \
                            --resource-group MyPatientSurveyRG \
                            --name ${GRAFANA_NAME} \
                            --image grafana/grafana \
                            --os-type Linux \
                            --cpu 1 \
                            --memory 2   
                            --ports 3000 \
                            --ip-address Public \
                            --location uksouth \
                            --environment-variables \
                                GF_SECURITY_ADMIN_USER=admin \
                                GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD} \
                            --no-wait
        
                        // Get public IPs
                        echo "Waiting for IP assignment..."
                        sleep 30  # Wait for IP assignment
                        PROMETHEUS_IP=$(az container show -g MyPatientSurveyRG -n ${PROMETHEUS_NAME} --query "ipAddress.ip" -o tsv)
                        GRAFANA_IP=$(az container show -g MyPatientSurveyRG -n ${GRAFANA_NAME} --query "ipAddress.ip" -o tsv)
        
                        echo "##[section] Monitoring Deployment Complete"
                        echo "Prometheus URL: http://${PROMETHEUS_IP}:9090"
                        echo "Grafana URL: http://${GRAFANA_IP}:3000"
                        echo "Grafana credentials: admin / ${GRAFANA_PASSWORD}"
        
                        // Store URLs for later use
                        echo "PROMETHEUS_URL=http://${PROMETHEUS_IP}:9090" > monitoring.env
                        echo "GRAFANA_URL=http://${GRAFANA_IP}:3000" >> monitoring.env
        
                        az logout
                        '''
                    }
                }
            }
        }

        stage('Configure Monitoring Firewall') {
            steps {
                script {
                    withCredentials([azureServicePrincipal('AZURE_CREDS')]) {
                        sh '''
                        az network nsg rule create \
                            --resource-group MyPatientSurveyRG \
                            --nsg-name default \
                            --name allow-grafana \
                            --priority 300 \
                            --access Allow \
                            --protocol Tcp \
                            --direction Inbound \
                            --source-address-prefixes '*' \
                            --source-port-ranges '*' \
                            --destination-address-prefixes '*' \
                            --destination-port-ranges 3000
        
                        az network nsg rule create \
                            --resource-group MyPatientSurveyRG \
                            --nsg-name default \
                            --name allow-prometheus \
                            --priority 310 \
                            --access Allow \
                            --protocol Tcp \
                            --direction Inbound \
                            --source-address-prefixes '*' \
                            --source-port-ranges '*' \
                            --destination-address-prefixes '*' \
                            --destination-port-ranges 9090
                        '''
                    }
                }
            }
        }
        stage('Install kubectl') {
          steps {
            sh '''#!/bin/bash
              set -e
              echo "Installing kubectl..."
              
              KUBE_DIR="$WORKSPACE/kubectl_install"
              mkdir -p "$KUBE_DIR/bin"
              
              curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
              chmod +x kubectl
              mv kubectl "$KUBE_DIR/bin/"
              
              export PATH="$KUBE_DIR/bin:$PATH"
              kubectl version --client --output=yaml
            '''
          }
        }
        stage('Deploy Infrastructure (Terraform)') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER_TF', passwordVariable: 'DB_PASSWORD_TF'),
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR')
                        ]) {
                            sh """
                                export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
                                export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
                                export ARM_TENANT_ID="${AZURE_TENANT_ID}"
                                export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"

                                export TF_VAR_db_user="${DB_USER_TF}"
                                export TF_VAR_db_password="${DB_PASSWORD_TF}"

                                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" -backend-config="storage_account_name=mypatientsurveytfstate" -backend-config="container_name=tfstate" -backend-config="key=patient_survey.tfstate"
                                terraform plan -out=tfplan.out -var="db_user=\${TF_VAR_db_user}" -var="db_password=\${TF_VAR_db_password}"
                                terraform apply -auto-approve tfplan.out
                            """
                            def sqlServerFqdn = sh(script: "terraform output -raw sql_server_fqdn", returnStdout: true).trim()
                            env.DB_HOST = sqlServerFqdn
                            env.DB_USER = DB_USER_TF
                            env.DB_PASSWORD = DB_PASSWORD_TF
                        }
                    }
                }
            }
        }

        stage('Create .env File') {
            steps {
                sh '''
                    echo "DB_HOST=${DB_HOST}" > app/.env
                    echo "DB_USER=${DB_USER}" >> app/.env
                    echo "DB_PASSWORD=${DB_PASSWORD}" >> app/.env
                    echo "DB_NAME=${DB_NAME}" >> app/.env

                    echo "Creating __init__.py files..."
                    touch app/__init__.py
                    touch app/utils/__init__.py
                '''
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    #!/usr/bin/env bash
                    set -e

                    echo "Installing ODBC Driver for SQL Server..."
                    export DEBIAN_FRONTEND=noninteractive
                    export TZ=Etc/UTC

                    sudo rm -f /var/lib/apt/lists/lock
                    sudo rm -f /var/cache/apt/archives/lock
                    sudo rm -f /var/lib/dpkg/lock-frontend
                    sudo dpkg --configure -a

                    sudo apt-get update
                    sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring python3-pip python3-venv

                    sudo rm -f /usr/share/keyrings/microsoft-prod.gpg
                    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor --batch -o /usr/share/keyrings/microsoft-prod.gpg

                    echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \\
                    | sudo tee /etc/apt/sources.list.d/mssql-release.list

                    sudo apt-get update
                    yes | sudo apt-get install -y msodbcsql17 unixodbc-dev

                    echo "Installing Python dependencies..."
                    python3 --version
                    pip3 install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }
       stage('Security Scan') {
          steps {
            dir('app') {
              sh '''#!/usr/bin/env bash
                set -ex
                
                # Install tools to user space
                python3 -m pip install --user bandit pip-audit
                
                # Add user's Python bin directory to PATH
                export PATH="$HOME/.local/bin:$PATH"
                echo "PATH is now: $PATH"
                
                # Verify tools are accessible
                which bandit || true
                which pip-audit || true
                
                # Run scans
                echo "Running Bandit scan..."
                bandit -r . -ll
                
                echo "Running pip-audit..."
                pip-audit -r ../requirements.txt --verbose
              '''
            }
          }
        } 
        stage('Run Tests') {
            steps {
                sh '''
                    export PATH=$HOME/.local/bin:$PATH
                    export DB_USER=${DB_USER}
                    export DB_PASSWORD=${DB_PASSWORD}
                    
                    if [ -z "$PYTHONPATH" ]; then
                        export PYTHONPATH=.
                    else
                        export PYTHONPATH=.:$PYTHONPATH
                    fi
                    
                    mkdir -p tests-results
                    touch tests/__init__.py

                    python3 -m xmlrunner discover -s tests -o test-results --failfast --verbose
                '''
            }
        }

    
        stage('Build Docker Image') {
            steps {
                script {
                    docker.build(IMAGE_TAG, '.')
                }
            }
        }
        
           stage('Deploy Application (Azure Container Instances)') {
            steps {
                script {
                    // Docker login and push with secure credential handling
                    withCredentials([usernamePassword(
                        credentialsId: 'docker-hub-creds',
                        usernameVariable: 'DOCKER_HUB_USER',
                        passwordVariable: 'DOCKER_HUB_PASSWORD'
                    )]) {
                        sh '''
                            echo "$DOCKER_HUB_PASSWORD" | docker login -u "$DOCKER_HUB_USER" --password-stdin
                            docker push ${IMAGE_TAG}
                        '''
                    }
        
                    // Azure deployment with secure credential handling
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID'),
                        usernamePassword(
                            credentialsId: 'docker-hub-creds',
                            usernameVariable: 'REGISTRY_USERNAME',
                            passwordVariable: 'REGISTRY_PASSWORD'
                        )
                    ]) {
                        sh '''
                            #!/bin/bash
                            set -e
        
                            echo "Logging into Azure..."
                            az login --service-principal \
                                -u "$ARM_CLIENT_ID" \
                                -p "$ARM_CLIENT_SECRET" \
                                --tenant "$ARM_TENANT_ID"
                            
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                            RESOURCE_GROUP_NAME="MyPatientSurveyRG"
                            ACI_NAME="patientsurvey-app-${BUILD_NUMBER}"
                            ACI_LOCATION="uksouth"
        
                            echo "Deploying Docker image ${IMAGE_TAG} to Azure Container Instances..."
                            az container create \
                                --resource-group $RESOURCE_GROUP_NAME \
                                --name $ACI_NAME \
                                --image ${IMAGE_TAG} \
                                --os-type Linux \
                                --cpu 1 \
                                --memory 1.5 \
                                --restart-policy Always \
                                --location $ACI_LOCATION \
                                --environment-variables \
                                    DB_HOST=${DB_HOST} \
                                    DB_USER=${DB_USER} \
                                    DB_PASSWORD=${DB_PASSWORD} \
                                    DB_NAME=${DB_NAME} \
                                --registry-login-server index.docker.io \
                                --registry-username "$REGISTRY_USERNAME" \
                                --registry-password "$REGISTRY_PASSWORD" \
                                --no-wait
        
                            echo "Azure Container Instance deployment initiated."
                            az logout
                        '''
                    }
                }
            }
        } 

    }
    post {
        always {
            junit 'test-results/*.xml'
            cleanWs()
        }
    }
}

        
    
