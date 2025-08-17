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
                        timeout(time: 15, unit: 'MINUTES') {
                            sh '''#!/bin/bash
                            set -eo pipefail
        
                            # ===== AUTHENTICATION =====
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                            # ===== GET APPLICATION IP =====
                            echo "🔍 Getting application container IP..."
                            APP_IP=$(az container show \
                                --resource-group MyPatientSurveyRG \
                                --name "patientsurvey-app-${BUILD_NUMBER}" \
                                --query "ipAddress.ip" \
                                -o tsv)
                            
                            if [ -z "$APP_IP" ]; then
                                echo "❌ ERROR: Failed to get application IP"
                                exit 1
                            fi
                            echo "✅ Application IP: $APP_IP"
        
                            # ===== DEPLOY PROMETHEUS =====
                            echo "📊 Deploying Prometheus..."
                            PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                            CONFIG_FILE="$WORKSPACE/infra/monitoring/prometheus.yml"
        
                            if [ ! -f "$CONFIG_FILE" ]; then
                                echo "❌ Error: prometheus.yml not found at $CONFIG_FILE"
                                exit 1
                            fi
        
                            # Update config with application IP
                            sed -i "s/DYNAMIC_APP_IP/${APP_IP}/g" "$CONFIG_FILE"
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
                                --dns-name-label "$GRAFANA_NAME" \
                                --location uksouth \
                                --environment-variables \
                                    GF_SECURITY_ADMIN_USER=admin \
                                    GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASSWORD"
        
                            # ===== VERIFY DEPLOYMENTS =====
                            echo "🔎 Verifying deployments..."
                            verify_container_ready() {
                                local name=$1
                                local max_retries=30
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
                                    elif [ "$state" == "Failed" ]; then
                                        echo "❌ Container $name deployment failed"
                                        az container logs -g MyPatientSurveyRG -n "$name" || true
                                        return 1
                                    fi
                                    
                                    echo "⌛ $name state: $state (attempt $i/$max_retries)"
                                    sleep $retry_interval
                                done
        
                                echo "❌ Timeout waiting for container $name to deploy"
                                az container logs -g MyPatientSurveyRG -n "$name" || true
                                return 1
                            }
        
                            verify_container_ready "$PROMETHEUS_NAME" || exit 1
                            verify_container_ready "$GRAFANA_NAME" || exit 1
        
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
        
                            # ===== WRITE CLEAN ENVIRONMENT FILE =====
                            echo "📝 Writing monitoring environment variables..."
                            cat > monitoring.env <<EOF
        PROMETHEUS_URL=http://${PROMETHEUS_IP}:9090
        GRAFANA_URL=http://${GRAFANA_IP}:3000
        GRAFANA_CREDS=admin:${GRAFANA_PASSWORD}
        APP_IP=${APP_IP}
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
        stage('Configure Monitoring') {
            steps {
                script {
                    // Verify and read the file
                    if (!fileExists('monitoring.env')) {
                        error("monitoring.env file not found")
                    }
                    
                    // Read and parse carefully
                    def envVars = [:]
                    readFile('monitoring.env').split('\n').each { line ->
                        line = line.trim()
                        if (line && line.contains('=')) {
                            def parts = line.split('=', 2)
                            envVars[parts[0]] = parts[1]
                        }
                    }
                    
                    // Validate required variables
                    def required = ['PROMETHEUS_URL', 'GRAFANA_URL', 'APP_IP']
                    def missing = required.findAll { !envVars[it]?.trim() }
                    
                    if (missing) {
                        error("Missing required variables: ${missing.join(', ')}")
                    }
                    
                    // Now use the variables
                    def PROMETHEUS_IP = envVars.PROMETHEUS_URL.replace('http://', '').replace(':9090', '')
                    def APP_IP = envVars.APP_IP
                    def GRAFANA_URL = envVars.GRAFANA_URL
        
        
                    // Update Prometheus config
                    sh """
                        cat <<EOF > prometheus-config.yml
                        global:
                          scrape_interval: 15s
                          evaluation_interval: 15s
        
                        scrape_configs:
                          - job_name: 'node-exporter'
                            static_configs:
                              - targets: ['${APP_IP}:9100']
                          - job_name: 'app-metrics'
                            static_configs:
                              - targets: ['${APP_IP}:8000']
                        EOF
        
                        echo "Updating Prometheus configuration..."
                        curl -v -X POST --data-binary @prometheus-config.yml http://${PROMETHEUS_IP}:9090/-/reload
                    """
        
                    // Setup Grafana dashboard
                    withCredentials([string(credentialsId: 'GRAFANA_PASSWORD', variable: 'GRAFANA_PASSWORD')]) {
                        sh """
                        echo "Waiting for Grafana to be ready..."
                        until curl -s ${GRAFANA_URL}/api/health; do sleep 5; done
        
                        echo "Adding Prometheus datasource..."
                        curl -v -X POST \
                          -H "Content-Type: application/json" \
                          -u admin:${GRAFANA_PASSWORD} \
                          -d '{
                            "name":"Prometheus",
                            "type":"prometheus",
                            "url":"http://${PROMETHEUS_IP}:9090",
                            "access":"proxy"
                          }' \
                          ${GRAFANA_URL}/api/datasources
        
                        echo "Importing dashboard..."
                        DASHBOARD_JSON='{
                          "dashboard": {
                            "title": "Application Metrics",
                            "panels": [
                              {
                                "title": "CPU Usage",
                                "type": "timeseries",
                                "datasource": "Prometheus",
                                "targets": [{"expr": "node_cpu_seconds_total"}],
                                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0}
                              },
                              {
                                "title": "Memory Usage",
                                "type": "timeseries",
                                "datasource": "Prometheus",
                                "targets": [{"expr": "node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes"}],
                                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 0}
                              }
                            ]
                          },
                          "overwrite": true
                        }'
        
                        curl -v -X POST \
                          -H "Content-Type: application/json" \
                          -u admin:${GRAFANA_PASSWORD} \
                          -d "\$DASHBOARD_JSON" \
                          ${GRAFANA_URL}/api/dashboards/db
                        """
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
      stage('Deploy Application') {
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
        
                        # Authenticate
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                        # Deploy app
                        ACI_NAME="patientsurvey-app-${BUILD_NUMBER}"
                        az container create \
                            --resource-group $RESOURCE_GROUP \
                            --name $ACI_NAME \
                            --image ${IMAGE_TAG} \
                            --os-type Linux \
                            --cpu 1 \
                            --memory 2 \
                            --ports 8000 9100 \
                            --restart-policy Always \
                            --location uksouth \
                            --ip-address Public \
                            --environment-variables \
                                DB_HOST=${DB_HOST} \
                                DB_USER=${DB_USER} \
                                DB_PASSWORD=${DB_PASSWORD} \
                                DB_NAME=${DB_NAME}
        
                        # Get app IP and write to file
                        APP_IP=$(az container show --resource-group $RESOURCE_GROUP --name $ACI_NAME --query "ipAddress.ip" -o tsv)
                        
                        # Create monitoring.env with all required variables
                        echo "Writing monitoring environment variables:"
                        echo "PROMETHEUS_URL=${PROMETHEUS_URL}" > monitoring.env
                        echo "GRAFANA_URL=${GRAFANA_URL}" >> monitoring.env
                        echo "GRAFANA_CREDS=${GRAFANA_CREDS}" >> monitoring.env
                        echo "APP_IP=${APP_IP}" >> monitoring.env
                        
                        echo "=== monitoring.env contents ==="
                        cat monitoring.env
                        echo "=============================="
                        '''
                    }
                }
            }
        }
        
        
        stage('Display Monitoring URLs') {
            steps {
                script {
                    def monitoringEnv = readFile('monitoring.env').trim()
                    def envVars = monitoringEnv.split('\n').collectEntries { it.split('=', 2) }

                    echo """
                    ========== MONITORING LINKS ==========
                    Prometheus: ${envVars['PROMETHEUS_URL']}
                    Grafana: ${envVars['GRAFANA_URL']} (admin:${envVars['GRAFANA_CREDS'].split(':')[1]})
                    Application Metrics: http://${envVars['APP_IP']}:8000/metrics
                    Node Metrics: http://${envVars['APP_IP']}:9100/metrics
                    =====================================
                    """
                }
            }
        }
    }

    post {
    always {
        junit 'test-results/*.xml'
        script {
            withCredentials([
                string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
            ]) {
                sh '''#!/bin/bash
                set -e
                echo "🧹 Post-build cleanup..."
                az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                az account set --subscription "$ARM_SUBSCRIPTION_ID"
                
                # Delete current build containers if pipeline failed
                if [ "$BUILD_RESULT" != "SUCCESS" ]; then
                    echo "⚠️ Pipeline failed - cleaning up current build containers"
                    az container delete \
                        --resource-group "$RESOURCE_GROUP" \
                        --name "patientsurvey-app-${BUILD_NUMBER}" \
                        --yes --no-wait || true
                    
                    az container delete \
                        --resource-group "$RESOURCE_GROUP" \
                        --name "prometheus-${BUILD_NUMBER}" \
                        --yes --no-wait || true
                    
                    az container delete \
                        --resource-group "$RESOURCE_GROUP" \
                        --name "grafana-${BUILD_NUMBER}" \
                        --yes --no-wait || true
                fi
                '''
            }
        }
        cleanWs()
    }
}
}
