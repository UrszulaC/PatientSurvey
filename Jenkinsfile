pipeline {
    agent any
    environment {
        DB_NAME = 'patient_survey_db'
        IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
        DOCKER_REGISTRY = "index.docker.io"
        RESOURCE_GROUP = 'MyPatientSurveyRG' 
    }

    options {
        timeout(time: 25, unit: 'MINUTES')
    }

    stages {
        stage('Clean Workspace') {
            steps {
                cleanWs()
            }
        }
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
        stage('Configure Network Security') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                    ]) {
                        sh '''#!/bin/bash
                        set -eo pipefail
        
                        echo "🔒 Configuring Network Security Rules..."
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                        NSG_NAME="monitoring-nsg"
                        RG_NAME="MyPatientSurveyRG"
        
                        # Check if NSG exists
                        if ! az network nsg show -g "$RG_NAME" -n "$NSG_NAME" &>/dev/null; then
                            echo "🛠️ Creating NSG $NSG_NAME..."
                            az network nsg create \
                                --resource-group "$RG_NAME" \
                                --name "$NSG_NAME" \
                                --location uksouth
                        fi
        
                        # Delete existing rules if they exist (idempotent)
                        echo "♻️ Removing existing rules if present..."
                        az network nsg rule delete \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowNodeExporter || true
                        
                        az network nsg rule delete \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowAppMetrics || true
        
                        # Add required rules with broader access
                        echo "➕ Adding Node Exporter rule (port 9100)..."
                        az network nsg rule create \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowNodeExporter \
                            --priority 310 \
                            --direction Inbound \
                            --access Allow \
                            --protocol Tcp \
                            --source-address-prefix Internet \
                            --source-port-range '*' \
                            --destination-address-prefix '*' \
                            --destination-port-range 9100 \
                            --description "Allow Prometheus scraping from anywhere"
        
                        echo "✅ Network security configured"
                        '''
                    }
                }
            }
        }
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
                        sh '''#!/bin/bash
                        set -eo pipefail
        
                        # ===== AUTHENTICATION =====
                        echo "🔑 Authenticating to Azure..."
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                        # ===== CONTAINER CLEANUP =====
                        echo "🧹 Cleaning up existing containers..."
                        CONTAINERS=$(az container list \
                            --resource-group MyPatientSurveyRG \
                            --query "[?provisioningState!='Deleting'].name" \
                            -o tsv)
        
                        if [ -n "$CONTAINERS" ]; then
                            echo "🗑️ Found containers to delete:"
                            echo "$CONTAINERS"
                            
                            # Serial deletion with proper error handling
                            for CONTAINER in $CONTAINERS; do
                                echo "➖ Deleting $CONTAINER..."
                                if ! az container delete \
                                    --resource-group MyPatientSurveyRG \
                                    --name "$CONTAINER" \
                                    --yes; then
                                    echo "⚠️ Failed to delete $CONTAINER, attempting force delete..."
                                    # Force delete by stopping first
                                    az container stop \
                                        --resource-group MyPatientSurveyRG \
                                        --name "$CONTAINER" \
                                        --yes || true
                                    az container delete \
                                        --resource-group MyPatientSurveyRG \
                                        --name "$CONTAINER" \
                                        --yes || true
                                fi
                            done
        
                            # Verify all containers are gone
                            echo "🔍 Verifying cleanup..."
                            MAX_RETRIES=10
                            for ((i=1; i<=$MAX_RETRIES; i++)); do
                                REMAINING=$(az container list \
                                    --resource-group MyPatientSurveyRG \
                                    --query "[].name" \
                                    -o tsv)
                                
                                if [ -z "$REMAINING" ]; then
                                    echo "✅ All containers deleted successfully"
                                    break
                                else
                                    echo "⌛ Containers remaining: $REMAINING"
                                    if [ $i -eq $MAX_RETRIES ]; then
                                        echo "❌ Critical: Containers still exist after $MAX_RETRIES attempts:"
                                        echo "$REMAINING"
                                        echo "Proceeding with deployment anyway..."
                                        break
                                    fi
                                    sleep 15
                                fi
                            done
                        else
                            echo "ℹ️ No containers found to delete"
                        fi
        
                        # ===== DEPLOY NEW MONITORING STACK =====
                        echo "🚀 Deploying new monitoring stack..."
                        PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                        GRAFANA_NAME="grafana-${BUILD_NUMBER}"
                        CONFIG_FILE="$WORKSPACE/infra/monitoring/prometheus.yml"
        
                        # Validate config file exists
                        if [ ! -f "$CONFIG_FILE" ]; then
                            echo "❌ Error: prometheus.yml not found at $CONFIG_FILE"
                            exit 1
                        fi
        
                        # ===== PROMETHEUS DEPLOYMENT =====
                        echo "📊 Deploying Prometheus ($PROMETHEUS_NAME)..."
                        CONFIG_BASE64=$(base64 -w0 "$CONFIG_FILE")
        
                        az container create \
                          --resource-group MyPatientSurveyRG \
                          --name "$PROMETHEUS_NAME" \
                          --image prom/prometheus:v2.47.0 \
                          --os-type Linux \
                          --cpu 0.5 \
                          --memory 1.5 \
                          --ports 9090 \
                          --ip-address Public \
                          --dns-name-label "$PROMETHEUS_NAME" \
                          --location uksouth \
                          --environment-variables \
                            PROMETHEUS_WEB_LISTEN_ADDRESS=0.0.0.0:9090 \
                            CONFIG_BASE64="$CONFIG_BASE64" \
                          --command-line "/bin/sh -c 'echo \"$CONFIG_BASE64\" | base64 -d > /etc/prometheus/prometheus.yml && exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.enable-lifecycle'"
        
                        # ===== GRAFANA DEPLOYMENT =====
                        echo "📈 Deploying Grafana ($GRAFANA_NAME)..."
                        az container create \
                            --resource-group MyPatientSurveyRG \
                            --name "$GRAFANA_NAME" \
                            --image grafana/grafana:9.5.6 \
                            --os-type Linux \
                            --cpu 0.5 \
                            --memory 1.5 \
                            --ports 3000 \
                            --ip-address Public \
                            --dns-name-label "$GRAFANA_NAME" \
                            --location uksouth \
                            --environment-variables \
                                GF_SECURITY_ADMIN_USER=admin \
                                GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASSWORD"
        
                        # ===== VERIFICATION =====
                        echo "🔎 Verifying deployments..."
                        verify_container_ready() {
                            local name=$1
                            local max_retries=15
                            local retry_interval=10
                            
                            for ((i=1; i<=max_retries; i++)); do
                                state=$(az container show \
                                    -g MyPatientSurveyRG \
                                    -n "$name" \
                                    --query "containers[0].instanceView.currentState.state" \
                                    -o tsv 2>/dev/null || echo "unknown")
                                
                                if [ "$state" == "Running" ]; then
                                    echo "✅ $name is running"
                                    return 0
                                else
                                    echo "⌛ $name state: $state (attempt $i/$max_retries)"
                                    sleep $retry_interval
                                fi
                            done
                            echo "❌ Failed to verify $name is running"
                            return 1
                        }
        
                        verify_container_ready "$PROMETHEUS_NAME"
                        verify_container_ready "$GRAFANA_NAME"
        
                        # Get endpoints
                        PROMETHEUS_IP=$(az container show \
                            -g MyPatientSurveyRG \
                            -n "$PROMETHEUS_NAME" \
                            --query "ipAddress.ip" \
                            -o tsv)
                        GRAFANA_IP=$(az container show \
                            -g MyPatientSurveyRG \
                            -n "$GRAFANA_NAME" \
                            --query "ipAddress.ip" \
                            -o tsv)
        
                        echo "✨ Deployment successful!"
                        echo "📊 Prometheus URL: http://$PROMETHEUS_IP:9090"
                        echo "📈 Grafana URL: http://$GRAFANA_IP:3000"
                        echo "🔑 Grafana Credentials: admin/$GRAFANA_PASSWORD"
        
                        # Write outputs
                        echo "PROMETHEUS_URL=http://$PROMETHEUS_IP:9090" > monitoring.env
                        echo "GRAFANA_URL=http://$GRAFANA_IP:3000" >> monitoring.env
                        echo "GRAFANA_CREDS=admin:$GRAFANA_PASSWORD" >> monitoring.env
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
                                
                                # Import the existing NSG
                                terraform import azurerm_network_security_group.monitoring_nsg /subscriptions/${AZURE_SUBSCRIPTION_ID_VAR}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Network/networkSecurityGroups/monitoring-nsg || true
                                
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
            withCredentials([usernamePassword(
                credentialsId: 'docker-hub-creds',
                usernameVariable: 'DOCKER_USER',
                passwordVariable: 'DOCKER_PASS'
            )]) {
                // Build and push in one step to ensure the image is available
                docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
                    docker.build(IMAGE_TAG, '.').push()
                }
                
                // Verify the image was pushed successfully
                sh """
                    docker pull ${IMAGE_TAG} || exit 1
                    echo "✅ Verified image ${IMAGE_TAG} exists in Docker Hub"
                """
            }
        }
    }
}

stage('Deploy Application (Azure Container Instances)') {
    steps {
        script {
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

                    # ===== AUTHENTICATION =====
                    echo "🔑 Authenticating to Azure..."
                    az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                    az account set --subscription "$ARM_SUBSCRIPTION_ID"

                    # ===== VERIFY IMAGE EXISTS =====
                    echo "🔍 Verifying Docker Hub image exists..."
                    if ! docker pull ${IMAGE_TAG}; then
                        echo "❌ ERROR: Image ${IMAGE_TAG} not found in Docker Hub!"
                        exit 1
                    fi

                    # ===== DEPLOY APPLICATION =====
                    echo "🚀 Deploying application container..."
                    RESOURCE_GROUP_NAME="MyPatientSurveyRG"
                    ACI_NAME="patientsurvey-app-${BUILD_NUMBER}"
                    ACI_LOCATION="uksouth"

                    az container create \
                        --resource-group $RESOURCE_GROUP_NAME \
                        --name $ACI_NAME \
                        --image ${IMAGE_TAG} \
                        --os-type Linux \
                        --cpu 1 \
                        --memory 2 \
                        --ports 8000 9100 \
                        --restart-policy Always \
                        --location $ACI_LOCATION \
                        --ip-address Public \
                        --environment-variables \
                            DB_HOST=${DB_HOST} \
                            DB_USER=${DB_USER} \
                            DB_PASSWORD=${DB_PASSWORD} \
                            DB_NAME=${DB_NAME} \
                        --registry-login-server index.docker.io \
                        --registry-username "$REGISTRY_USERNAME" \
                        --registry-password "$REGISTRY_PASSWORD"
        
                            # ===== GET APPLICATION IP =====
                            echo "🔄 Getting application IP..."
                            MAX_RETRIES=10
                            RETRY_DELAY=10
                            APP_IP=""
                            
                            for i in $(seq 1 $MAX_RETRIES); do
                                APP_IP=$(az container show \
                                    --resource-group $RESOURCE_GROUP_NAME \
                                    --name $ACI_NAME \
                                    --query "ipAddress.ip" \
                                    --output tsv)
                                
                                if [ -n "$APP_IP" ]; then
                                    echo "✅ Application IP: $APP_IP"
                                    break
                                else
                                    echo "Attempt $i/$MAX_RETRIES: IP not yet assigned..."
                                    sleep $RETRY_DELAY
                                fi
                            done
        
                            if [ -z "$APP_IP" ]; then
                                echo "❌ ERROR: Failed to get IP address after $MAX_RETRIES attempts"
                                exit 1
                            fi
        
                            # ===== VERIFY METRICS ENDPOINTS =====
                            echo "🔍 Testing metrics endpoints..."
                            MAX_RETRIES=5
                            RETRY_DELAY=10
                            
                            # Get container logs for debugging
                            echo "Container logs:"
                            az container logs --resource-group $RESOURCE_GROUP_NAME --name $ACI_NAME
                            
                            # Test node-exporter with enhanced diagnostics
                            for i in $(seq 1 $MAX_RETRIES); do
                                if curl -v --connect-timeout 5 "http://${APP_IP}:9100/metrics" >/dev/null; then
                                    echo "✅ node_exporter is reachable"
                                    break
                                else
                                    echo "Attempt $i/$MAX_RETRIES: node_exporter not ready..."
                                    [ $i -eq $MAX_RETRIES ] && {
                                        echo "❌ node_exporter failed after $MAX_RETRIES attempts"
                                        echo "Debug info:"
                                        az container exec --resource-group $RESOURCE_GROUP_NAME --name $ACI_NAME --exec-command "ps aux"
                                        exit 1
                                    }
                                    sleep $RETRY_DELAY
                                fi
                            done
        
                            # ===== UPDATE PROMETHEUS CONFIG =====
                            echo "🔄 Updating Prometheus configuration..."
                            CONFIG_FILE="$WORKSPACE/infra/monitoring/prometheus.yml"
                            TMP_CONFIG="/tmp/prometheus-${BUILD_NUMBER}.yml"
        
                            # Replace placeholder with actual IP
                            sed "s/DYNAMIC_APP_IP/${APP_IP}/g" "$CONFIG_FILE" > "$TMP_CONFIG"
        
                            # Verify substitution
                            echo "=== Generated Prometheus Config ==="
                            cat "$TMP_CONFIG"
                            echo "=================================="
        
                            if grep -q "DYNAMIC_APP_IP" "$TMP_CONFIG"; then
                                echo "❌ ERROR: Variable substitution failed in Prometheus config!"
                                exit 1
                            fi
        
                            CONFIG_BASE64=$(base64 -w0 "$TMP_CONFIG")
        
                            # ===== DEPLOY PROMETHEUS =====
                            echo "📊 Redeploying Prometheus with updated config..."
                            PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                            
                            # Delete existing Prometheus if exists
                            if az container show --resource-group $RESOURCE_GROUP_NAME --name $PROMETHEUS_NAME &>/dev/null; then
                                echo "♻️ Removing existing Prometheus..."
                                az container delete \
                                    --resource-group $RESOURCE_GROUP_NAME \
                                    --name $PROMETHEUS_NAME \
                                    --yes
                            fi
        
                            # Create new Prometheus instance
                            az container create \
                                --resource-group $RESOURCE_GROUP_NAME \
                                --name $PROMETHEUS_NAME \
                                --image prom/prometheus:v2.47.0 \
                                --os-type Linux \
                                --cpu 0.5 \
                                --memory 1.5 \
                                --ports 9090 \
                                --ip-address Public \
                                --dns-name-label "$PROMETHEUS_NAME" \
                                --location $ACI_LOCATION \
                                --command-line "/bin/sh -c 'echo \"$CONFIG_BASE64\" | base64 -d > /etc/prometheus/prometheus.yml && exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.enable-lifecycle'"
        
                            # ===== VERIFY DEPLOYMENT =====
                            echo "🔍 Verifying Prometheus deployment..."
                            PROMETHEUS_IP=$(az container show \
                                -g $RESOURCE_GROUP_NAME \
                                -n "$PROMETHEUS_NAME" \
                                --query "ipAddress.ip" \
                                -o tsv)
        
                            echo "✅ Deployment successful!"
                            echo "📊 Prometheus URL: http://${PROMETHEUS_IP}:9090"
                            echo "📈 Application Metrics: http://${APP_IP}:8000/metrics"
                            echo "🖥️ Node Metrics: http://${APP_IP}:9100/metrics"
        
                            # Write outputs for downstream jobs
                            echo "PROMETHEUS_URL=http://${PROMETHEUS_IP}:9090" > monitoring.env
                            echo "APP_METRICS_URL=http://${APP_IP}:8000/metrics" >> monitoring.env
                            echo "NODE_METRICS_URL=http://${APP_IP}:9100/metrics" >> monitoring.env
        
                            az logout
                        '''
                    }
                }
            }
        }
        stage('Configure Dynamic Monitoring') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                    ]) {
                        // 1. Get the ACI IP
                        ACI_IP = sh(script: '''
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID" > /dev/null
                            az account set --subscription "$ARM_SUBSCRIPTION_ID" > /dev/null
                            az container show -g MyPatientSurveyRG -n patientsurvey-app-${BUILD_NUMBER} --query ipAddress.ip -o tsv
                        ''', returnStdout: true).trim()
        
                        if (!ACI_IP?.trim()) {
                            error("Failed to get ACI IP address")
                        }
        
                        // 2. Update Prometheus config
                        def prometheusConfig = "${WORKSPACE}/infra/monitoring/prometheus.yml"
                        
                        sh """
                            # Create backup
                            cp -v "${prometheusConfig}" "${prometheusConfig}.bak"
                            
                            # Update config (using alternative delimiter)
                            sed -i "s|DYNAMIC_APP_IP|${ACI_IP}|g" "${prometheusConfig}"
                            
                            # Verify change
                            grep "${ACI_IP}" "${prometheusConfig}" || {
                                echo "ERROR: IP substitution failed"
                                exit 1
                            }
                        """
        
                        // 3. Reload Prometheus
                        sh """
                            curl -v -X POST http://${env.PROMETHEUS_SERVER}:9090/-/reload || {
                                echo "ERROR: Prometheus reload failed"
                                exit 1
                            }
                        """
                    }
                }
            }
        }
        stage('Verify Monitoring') {
            steps {
                script {
                    // Wait for metrics to appear
                    timeout(time: 2, unit: 'MINUTES') {
                        waitUntil {
                            def metrics = sh(script: """
                                curl -s http://${PROMETHEUS_SERVER}:9090/api/v1/targets | \
                                jq '.data.activeTargets[] | select(.labels.instance=="${ACI_IP}:9100")'
                            """, returnStdout: true)
                            return metrics.contains('"health":"up"')
                        }
                    }
                }
            }
        }
        stage('Update Grafana Dashboard') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'GRAFANA_SERVICE_ACCOUNT_TOKEN', variable: 'GRAFANA_TOKEN')
                    ]) {
                        sh """
                        curl -X POST \
                          -H "Authorization: Bearer ${GRAFANA_TOKEN}" \
                          -H "Content-Type: application/json" \
                          -d '{
                            "dashboard": {
                              "title": "ACI-${BUILD_NUMBER}",
                              "panels": [{
                                "title": "CPU Usage",
                                "type": "timeseries",  // Note: "timeseries" replaces "graph" in Grafana 10+
                                "datasource": "Prometheus",
                                "targets": [{
                                  "expr": "node_cpu_seconds_total{instance=~\"${APP_IP}:.+\"}"
                                }]
                              }]
                            },
                            "overwrite": true
                          }' \
                          "${GRAFANA_URL}/api/dashboards/db
                        """
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
        failure {
            script {
                withCredentials([
                    string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                    string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                    string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                    string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                ]) {
                    sh '''
                    # Clean up monitoring on failure
                    az login --service-principal -u $ARM_CLIENT_ID -p $ARM_CLIENT_SECRET --tenant $ARM_TENANT_ID
                    az account set --subscription $ARM_SUBSCRIPTION_ID
                    az container delete --yes --no-wait \
                        --resource-group MyPatientSurveyRG \
                        --name prometheus-${BUILD_NUMBER} || true
                    az container delete --yes --no-wait \
                        --resource-group MyPatientSurveyRG \
                        --name grafana-${BUILD_NUMBER} || true
                    '''
                }
            }
        }
    }
}
    
