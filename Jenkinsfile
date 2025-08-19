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
                        PIDS=$(sudo fuser -k "$lock_file" 2>/dev/null || true)
                        if [ -n "$PIDS" ]; then
                            echo "Killed processes holding $lock_file: $PIDS"
                        fi
                        sudo rm -f "$lock_file"
                    fi
                done
    
                # Ensure dpkg is configured correctly after potential crashes
                sudo dpkg --configure -a || true
                echo "Environment cleanup complete."
                '''
            }
        }
        
        stage('Checkout Code') {
            steps {
                checkout scm
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
        stage('Prepare Prometheus Config') {
            steps {
                sh '''
                # Ensure APP_IP is set in Jenkins environment
                echo "Using APP_IP=${APP_IP}"
        
                # Generate Prometheus config dynamically
                cat > prometheus.yml <<EOL
        global:
          scrape_interval: 15s
          evaluation_interval: 15s
          scrape_timeout: 10s
        
        scrape_configs:
          # Prometheus self-monitoring
          - job_name: 'prometheus'
            static_configs:
              - targets: ['localhost:9090']
        
          # Patient Survey CLI app metrics
          - job_name: 'patient-survey-app'
            static_configs:
              - targets: ['${APP_IP}:8001']
        
          # Node exporter metrics (inside app container)
          - job_name: 'myapp-node'
            static_configs:
              - targets: ['${APP_IP}:9100']
        EOL
        
                # Start Prometheus with the generated config
                nohup prometheus --config.file=prometheus.yml > prometheus.log 2>&1 &
                echo "Prometheus started with dynamic config"
                '''
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
                        docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
                            docker.build(IMAGE_TAG, '.').push()
                        }
                        
                        sh """
                            docker pull ${IMAGE_TAG} || exit 1
                            echo "✅ Verified image ${IMAGE_TAG} exists in Docker Hub"
                        """
                    }
                }
            }
        }
        
        stage('Cleanup Old Containers') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                    ]) {
                        sh '''#!/bin/bash
                        set -e
        
                        echo "🔑 Authenticating to Azure..."
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                        echo "🧹 Cleaning up old containers..."
                        # List all containers except current build
                        CONTAINERS=$(az container list \
                            --resource-group "$RESOURCE_GROUP" \
                            --query "[?name!='patientsurvey-app-${BUILD_NUMBER}' && name!='prometheus-${BUILD_NUMBER}' && name!='grafana-${BUILD_NUMBER}'].name" \
                            -o tsv)
                        
                        if [ -n "$CONTAINERS" ]; then
                            echo "🗑️ Found containers to delete:"
                            echo "$CONTAINERS"
                            
                            # Delete containers sequentially and wait for completion
                            for CONTAINER in $CONTAINERS; do
                                echo "➖ Deleting $CONTAINER..."
                                az container delete \
                                    --resource-group "$RESOURCE_GROUP" \
                                    --name "$CONTAINER" \
                                    --yes
                                echo "✅ $CONTAINER deleted"
                            done
                        else
                            echo "ℹ️ No old containers found to delete"
                        fi
        
                        # Verify quota is available
                        echo "🔄 Checking available quota..."
                        QUOTA=$(az vm list-usage --location uksouth --query "[?localName=='Standard Cores'].{limit:limit, currentValue:currentValue}" -o json)
                        echo "Current quota usage: $QUOTA"
                        '''
                    }
                }
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

                        az network nsg rule create \
                            --resource-group MyPatientSurveyRG \
                            --nsg-name monitoring-nsg \
                            --name AllowAppMetrics \
                            --priority 320 \
                            --direction Inbound \
                            --access Allow \
                            --protocol Tcp \
                            --source-address-prefix Internet \
                            --source-port-range '*' \
                            --destination-address-prefix '*' \
                            --destination-port-range 8001 \
                            --description "Allow Prometheus to scrape application metrics"
        
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
                        timeout(time: 15, unit: 'MINUTES') {
                            sh '''#!/bin/bash
                            set -eo pipefail
       
                            # ===== AUTHENTICATION =====
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
       
                            # ===== DEPLOY PROMETHEUS =====
                            echo "📊 Deploying Prometheus..."
                            PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                            CONFIG_FILE="$WORKSPACE/infra/monitoring/prometheus.yml"
       
                            if [ ! -f "$CONFIG_FILE" ]; then
                                echo "❌ Error: prometheus.yml not found at $CONFIG_FILE"
                                exit 1
                            fi
       
                            # Use placeholder IP initially
                            sed -i "s/DYNAMIC_APP_IP/PLACEHOLDER_IP/g" "$CONFIG_FILE"
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
                             --dns-name-label "prometheus-survey" \
                             --location uksouth \
                             --command-line "/bin/sh -c 'echo \"$CONFIG_BASE64\" | base64 -d > /etc/prometheus/prometheus.yml && exec /bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.enable-lifecycle'"
       
                            # ===== DEPLOY GRAFANA =====
                            echo "📈 Deploying Grafana..."
                            GRAFANA_NAME="grafana-${BUILD_NUMBER}"
       
                            az container create \
                                --resource-group MyPatientSurveyRG \
                                --name "$GRAFANA_NAME" \
                                --image grafana/grafana:9.5.6 \
                                --os-type Linux \
                                --cpu 0.5 \
                                --memory 1.5 \
                                --ports 3000 \
                                --ip-address Public \
                                --dns-name-label "grafana-survey" \
                                --location uksouth \
                                --environment-variables \
                                    GF_SECURITY_ADMIN_USER=admin \
                                    GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASSWORD"
       
                            # ===== GET MONITORING ENDPOINTS =====
                            echo "🔗 Getting monitoring endpoints..."
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
       
                            # ===== WRITE MONITORING ENV FILE =====
                            echo "📝 Writing monitoring environment variables..."
                            cat > monitoring.env <<EOF
                            PROMETHEUS_URL=http://${PROMETHEUS_IP}:9090
                            GRAFANA_URL=http://${GRAFANA_IP}:3000
                            GRAFANA_CREDS=admin:${GRAFANA_PASSWORD}
                            EOF
       
                            echo "=== monitoring.env contents ==="
                            cat monitoring.env
                            echo "=============================="
                            '''
                        }
                    }
                }
            }
        }
        
        stage('Deploy Application') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID'),
                        usernamePassword(
                            credentialsId: 'docker-hub-creds',
                            usernameVariable: 'DOCKER_HUB_USER',
                            passwordVariable: 'DOCKER_HUB_PASSWORD'
                        )
                    ]) {
                        timeout(time: 10, unit: 'MINUTES') {
                            sh '''#!/bin/bash
                            set -eo pipefail
        
                            # ===== AUTHENTICATION =====
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                            # ===== VERIFY IMAGE EXISTS =====
                            echo "🔍 Verifying Docker image exists..."
                            if ! docker login -u "$DOCKER_HUB_USER" -p "$DOCKER_HUB_PASSWORD"; then
                                echo "❌ ERROR: Failed to login to Docker Hub"
                                exit 1
                            fi
                            
                            if ! docker pull ${IMAGE_TAG}; then
                                echo "❌ ERROR: Failed to pull image ${IMAGE_TAG}"
                                echo "Please verify:"
                                echo "1. The image exists in Docker Hub"
                                echo "2. The credentials have proper permissions"
                                echo "3. The image tag is correct"
                                exit 1
                            fi
                            echo "✅ Image verified successfully"
        
                            # ===== DEPLOY APPLICATION =====
                            echo "🚀 Deploying application container..."
                            ACI_NAME="patientsurvey-app-${BUILD_NUMBER}"
                            az container create \
                                --resource-group MyPatientSurveyRG \
                                --name $ACI_NAME \
                                --image ${IMAGE_TAG} \
                                --os-type Linux \
                                --cpu 1 \
                                --memory 2 \
                                --ports 9100 \
                                --restart-policy Always \
                                --location uksouth \
                                --ip-address Public \
                                --environment-variables \
                                    DB_HOST=${DB_HOST} \
                                    DB_USER=${DB_USER} \
                                    DB_PASSWORD=${DB_PASSWORD} \
                                    DB_NAME=${DB_NAME} \
                                --registry-login-server index.docker.io \
                                --registry-username "$DOCKER_HUB_USER" \
                                --registry-password "$DOCKER_HUB_PASSWORD" \
                                --command-line "python3 -m app.main --host 0.0.0.0 --port 8001"
        
                            # ===== GET APPLICATION IP =====
                            echo "🔄 Getting application IP..."
                            MAX_RETRIES=10
                            RETRY_DELAY=10
                            APP_IP=""
                            
                            for ((i=1; i<=$MAX_RETRIES; i++)); do
                                APP_IP=$(az container show \
                                    --resource-group MyPatientSurveyRG \
                                    --name $ACI_NAME \
                                    --query "ipAddress.ip" \
                                    -o tsv)
                                
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
        
                            # Update monitoring.env with application IP
                            echo "APP_IP=$APP_IP" >> monitoring.env
                            '''
                        }
                    }
                }
            }
        }
        
            stage('Configure Monitoring') {
                steps {
                    script {
                        // Read monitoring.env
                        def monitoringEnv = readFile('monitoring.env').trim()
                        def envVars = [:]
                        monitoringEnv.split('\n').each { line ->
                            def parts = line.split('=', 2)
                            if (parts.size() == 2) {
                                envVars[parts[0].trim()] = parts[1].trim()
                            }
                        }
            
                        def requiredVars = ['PROMETHEUS_URL', 'GRAFANA_URL', 'APP_IP']
                        def missingVars = requiredVars.findAll { !envVars[it] }
                        if (missingVars) {
                            error("Missing required monitoring environment variables: ${missingVars.join(', ')}")
                        }
            
                        sh """
                            PROMETHEUS_IP=\$(echo "${envVars['PROMETHEUS_URL']}" | sed 's|http://||;s|:9090||')
            
                            cat <<EOF > prometheus-config.yml
                            global:
                              scrape_interval: 15s
                              evaluation_interval: 15s
            
                            scrape_configs:
                              - job_name: 'node-exporter'
                                static_configs:
                                  - targets: ['${envVars['APP_IP']}:9100']
            
                              - job_name: 'app-metrics'
                                static_configs:
                                  - targets: ['${envVars['APP_IP']}:8001']
                            EOF
            
                            curl -X POST --data-binary @prometheus-config.yml http://\${PROMETHEUS_IP}:9090/-/reload || echo "⚠️ Prometheus reload failed (might need manual configuration)"
                        """
                    }
                }
            }

            
            stage('Display Monitoring URLs') {
                steps {
                    withCredentials([string(credentialsId: 'GRAFANA_PASSWORD', variable: 'GRAFANA_PASSWORD')]) {
                        sh '''#!/bin/bash
                            # Load variables from monitoring.env
                            source monitoring.env
                            
                            echo "========== MONITORING LINKS =========="
                            echo "Prometheus Dashboard: $PROMETHEUS_URL"
                            echo "Grafana Dashboard: $GRAFANA_URL"
                            echo "Node Metrics: http://$APP_IP:9100/metrics"
                            echo "Patient Survey App Metrics: http://$APP_IP:8001/metrics"
                            echo "====================================="
                        '''
                    }
                }
            }
        
    }
    post {
        always {
            junit 'test-results/*.xml'
            // Only workspace cleanup remains
            cleanWs()
        }
    }
}



