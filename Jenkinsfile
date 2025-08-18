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
        
                        # Create NSG if it doesn't exist
                        if ! az network nsg show -g "$RG_NAME" -n "$NSG_NAME" &>/dev/null; then
                            echo "🛠️ Creating NSG $NSG_NAME..."
                            az network nsg create --resource-group "$RG_NAME" --name "$NSG_NAME" --location uksouth
                        fi
        
                        # Add Prometheus rule (9090)
                        echo "➕ Adding Prometheus rule..."
                        az network nsg rule create \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowPrometheus \
                            --priority 310 \
                            --direction Inbound \
                            --access Allow \
                            --protocol Tcp \
                            --source-address-prefix Internet \
                            --source-port-range '*' \
                            --destination-address-prefix '*' \
                            --destination-port-range 9090
        
                        # Add Grafana rule (3000)
                        echo "➕ Adding Grafana rule..."
                        az network nsg rule create \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowGrafana \
                            --priority 320 \
                            --direction Inbound \
                            --access Allow \
                            --protocol Tcp \
                            --source-address-prefix Internet \
                            --source-port-range '*' \
                            --destination-address-prefix '*' \
                            --destination-port-range 3000
        
                        # Add App Metrics rule (8000)
                        echo "➕ Adding App Metrics rule..."
                        az network nsg rule create \
                            --resource-group "$RG_NAME" \
                            --nsg-name "$NSG_NAME" \
                            --name AllowAppMetrics \
                            --priority 330 \
                            --direction Inbound \
                            --access Allow \
                            --protocol Tcp \
                            --source-address-prefix Internet \
                            --source-port-range '*' \
                            --destination-address-prefix '*' \
                            --destination-port-range 8000
        
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
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                            # Prometheus + Grafana deployment here...
        
                            echo "📝 Creating monitoring.env..."
                            cat > monitoring.env <<EOF
                            PROMETHEUS_URL=http://${PROMETHEUS_IP}:9090
                            GRAFANA_URL=http://${GRAFANA_IP}:3000
                            GRAFANA_CREDS=admin:${GRAFANA_PASSWORD}
                            EOF
        
                            if [ ! -f monitoring.env ]; then
                                echo "❌ ERROR: Failed to create monitoring.env"
                                exit 1
                            fi
        
                            echo "=== monitoring.env contents ==="
                            cat monitoring.env
                            echo "=============================="
                            '''
                            archiveArtifacts artifacts: 'monitoring.env', allowEmptyArchive: false
                        }
                    }
                }
            }
        }

        stage('Deploy Application') {
            steps {
                script {
                    // Pre-check workspace
                    sh '''
                    echo "=== Pre-unarchive workspace contents ==="
                    ls -la
                    echo "=============================="
                    '''
        
                    unarchive mapping: ['monitoring.env': 'monitoring.env'], fingerprintArtifacts: true
        
                    sh '''
                    echo "=== Post-unarchive workspace contents ==="
                    ls -la
                    echo "=== monitoring.env contents ==="
                    cat monitoring.env || true
                    echo "=============================="
                    '''
        
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
        
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                            echo "🔍 Verifying Docker image exists..."
                            docker login -u "$DOCKER_HUB_USER" -p "$DOCKER_HUB_PASSWORD"
                            docker pull ${IMAGE_TAG}
        
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
                                --command-line "python3 -m app.main"
        
                            echo "🔄 Getting application IP..."
                            APP_IP=$(az container show \
                                --resource-group MyPatientSurveyRG \
                                --name $ACI_NAME \
                                --query "ipAddress.ip" -o tsv)
        
                            echo "APP_IP=$APP_IP" >> monitoring.env
                            '''
                            archiveArtifacts artifacts: 'monitoring.env', fingerprint: true
                        }
                    }
                }
            }
        }

        
        stage('Configure Monitoring') {
                    steps {
                        script {
                            // Verify workspace state before unarchiving
                            sh '''
                            echo "=== Pre-configure workspace contents ==="
                            ls -la
                            echo "=============================="
                            '''
                            
                            // Force unarchive with verification
                            unarchive mapping: [
                                'monitoring.env': 'monitoring.env'
                            ], fingerprintArtifacts: true, quiet: false
                            
                            // Verify file exists and has content
                            sh '''
                            if [ ! -f monitoring.env ]; then
                                echo "❌ ERROR: monitoring.env missing!"
                                exit 1
                            fi
                            
                            if [ ! -s monitoring.env ]; then
                                echo "❌ ERROR: monitoring.env is empty!"
                                exit 1
                            fi
                            
                            echo "=== monitoring.env contents ==="
                            cat monitoring.env
                            echo "=============================="
                            '''
                            
                            // Read with better error handling
                            try {
                                def monitoringEnv = readFile('monitoring.env').trim()
                                echo "Raw monitoring.env content:\n${monitoringEnv}"
                                
                                def envVars = [:]
                                monitoringEnv.eachLine { line ->
                                    if (line.trim() && !line.startsWith("#")) {
                                        def parts = line.split('=', 2)
                                        if (parts.size() == 2) {
                                            envVars[parts[0].trim()] = parts[1].trim()
                                        }
                                    }
                                }
                            } catch (FileNotFoundException e) {
                                error "Failed to read monitoring.env file: ${e.getMessage()}"
                            }
                            
                            withCredentials([
                                string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                                string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                                string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                                string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                            ]) {
                                // Reconfigure Prometheus config file with the new application IP
                                sh """
                                    # Re-authenticating with Azure is a good practice here
                                    echo "🔑 Re-authenticating to Azure..."
                                    az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                                    az account set --subscription "$ARM_SUBSCRIPTION_ID"
                
                                    echo "🔄 Updating Prometheus configuration with new app IP..."
                                    APP_IP=$(az container show --resource-group MyPatientSurveyRG --name patientsurvey-app-${BUILD_NUMBER} --query "ipAddress.ip" -o tsv)
                
                                    if [ -z "\$APP_IP" ]; then
                                        echo "❌ ERROR: Could not get application IP."
                                        exit 1
                                    fi
                
                                    PROMETHEUS_CONFIG_PATH="/etc/prometheus/prometheus.yml"
                                    TEMP_CONFIG_PATH="/tmp/prometheus.yml"
                
                                    # Get account key for the file share
                                    FILE_SHARE_KEY=$(az storage account keys list --resource-group MyPatientSurveyRG --account-name mypatientsurveytfstate --query '[0].value' -o tsv)
                
                                    # Mount the file share and copy the existing config
                                    # Note: This is a complex operation in Jenkins.
                                    # A better approach might be to use a separate container or a tool that can directly update the file share content.
                                    # For this example, we assume we can update the content directly.
                
                                    # Simplified for demonstration: Create a new config and upload it
                                    cat > /tmp/prometheus-updated.yml <<EOF
                    global:
                      scrape_interval: 15s
                      evaluation_interval: 15s
                    scrape_configs:
                      - job_name: 'app-metrics'
                        static_configs:
                          - targets: ['\${APP_IP}:9100']
                    EOF

                    # Upload the updated file to the Azure File Share
                    az storage file upload --account-name mypatientsurveytfstate --share-name tfstate --source "/tmp/prometheus-updated.yml" --path "prometheus/prometheus.yml" --account-key "\$FILE_SHARE_KEY"
                    echo "✅ Prometheus configuration updated on Azure File Share"
                """
            }
        }
    }
}
        
            
            stage('Display Monitoring URLs') {
                steps {
                    sh '''#!/bin/bash
                    echo "========== MONITORING LINKS =========="
                    echo "Prometheus Dashboard: $(grep PROMETHEUS_URL monitoring.env | cut -d= -f2)"
                    echo "Grafana Dashboard: $(grep GRAFANA_URL monitoring.env | cut -d= -f2)"
                    echo "Node Metrics: http://$(grep APP_IP monitoring.env | cut -d= -f2):9100/metrics"
                    echo "====================================="
                    '''
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
