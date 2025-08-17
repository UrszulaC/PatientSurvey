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

                        # Authenticate to Azure
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"

                        # Deploy Prometheus with basic config
                        PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                        az container create \
                          --resource-group $RESOURCE_GROUP \
                          --name "$PROMETHEUS_NAME" \
                          --image prom/prometheus:v2.47.0 \
                          --os-type Linux \
                          --cpu 1.0 \
                          --memory 2.0 \
                          --ports 9090 \
                          --ip-address Public \
                          --dns-name-label "$PROMETHEUS_NAME" \
                          --location uksouth \
                          --command-line "/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.enable-lifecycle"

                        # Deploy Grafana with pre-configured dashboard
                        GRAFANA_NAME="grafana-${BUILD_NUMBER}"
                        az container create \
                            --resource-group $RESOURCE_GROUP \
                            --name "$GRAFANA_NAME" \
                            --image grafana/grafana:9.5.6 \
                            --os-type Linux \
                            --cpu 1.0 \
                            --memory 2.0 \
                            --ports 3000 \
                            --ip-address Public \
                            --dns-name-label "$GRAFANA_NAME" \
                            --location uksouth \
                            --environment-variables \
                                GF_SECURITY_ADMIN_USER=admin \
                                GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASSWORD"

                        # Get endpoints
                        PROMETHEUS_IP=$(az container show -g $RESOURCE_GROUP -n "$PROMETHEUS_NAME" --query "ipAddress.ip" -o tsv)
                        GRAFANA_IP=$(az container show -g $RESOURCE_GROUP -n "$GRAFANA_NAME" --query "ipAddress.ip" -o tsv)

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

                        # Get app IP
                        APP_IP=$(az container show --resource-group $RESOURCE_GROUP --name $ACI_NAME --query "ipAddress.ip" -o tsv)
                        echo "APP_IP=$APP_IP" >> monitoring.env
                        '''
                    }
                }
            }
        }

        stage('Configure Monitoring') {
            steps {
                script {
                    // Read monitoring endpoints more reliably
                    def monitoringEnv = readFile('monitoring.env').trim()
                    def envVars = [:]
                    monitoringEnv.eachLine { line ->
                        def parts = line.split('=', 2)
                        if (parts.size() == 2) {
                            envVars[parts[0]] = parts[1]
                        }
                    }
                    
                    if (!envVars.PROMETHEUS_URL || !envVars.GRAFANA_URL || !envVars.APP_IP) {
                        error("Missing required monitoring environment variables")
                    }
        
                    def PROMETHEUS_IP = envVars.PROMETHEUS_URL.replace('http://', '').replace(':9090', '')
                    def APP_IP = envVars.APP_IP
        
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
        
                        # Send config to Prometheus
                        curl -X POST --data-binary @prometheus-config.yml http://${PROMETHEUS_IP}:9090/-/reload
                    """
        
                    // Setup Grafana dashboard
                    withCredentials([string(credentialsId: 'GRAFANA_PASSWORD', variable: 'GRAFANA_PASSWORD')]) {
                        sh """
                        # Wait for Grafana to be ready
                        until curl -s ${envVars.GRAFANA_URL}/api/health; do sleep 5; done
        
                        # Add Prometheus datasource
                        curl -X POST \
                          -H "Content-Type: application/json" \
                          -u admin:${GRAFANA_PASSWORD} \
                          -d '{
                            "name":"Prometheus",
                            "type":"prometheus",
                            "url":"http://${PROMETHEUS_IP}:9090",
                            "access":"proxy"
                          }' \
                          ${envVars.GRAFANA_URL}/api/datasources
        
                        # Import simple dashboard
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
        
                        curl -X POST \
                          -H "Content-Type: application/json" \
                          -u admin:${GRAFANA_PASSWORD} \
                          -d "\$DASHBOARD_JSON" \
                          ${envVars.GRAFANA_URL}/api/dashboards/db
                        """
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
            cleanWs()
        }
    }
}
