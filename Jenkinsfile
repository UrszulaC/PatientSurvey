pipeline {
    agent any
    environment {
        // Define common variables here
        RESOURCE_GROUP = "MyPatientSurveyRG"
    }
    stages {
        stage('Checkout & Build') {
            steps {
                echo "Skipping source checkout and build steps as they are not provided."
                sh 'echo "Simulating build and image creation..."'
                script {
                    // This is a placeholder for where the real build and tagging would occur
                    env.IMAGE_TAG = "your-docker-username/patientsurvey-app:latest"
                    echo "Image tag set to: ${env.IMAGE_TAG}"
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
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID" > /dev/null
                        az account set --subscription "$ARM_SUBSCRIPTION_ID" > /dev/null

                        NSG_NAME="monitoring-nsg"
                        RG_NAME="MyPatientSurveyRG"

                        # Check if NSG exists
                        if ! az network nsg show -g "$RG_NAME" -n "$NSG_NAME" &>/dev/null; then
                            echo "🛠️ Creating NSG $NSG_NAME..."
                            az network nsg create \
                                --resource-group "$RG_NAME" \
                                --name "$NSG_NAME" \
                                --location uksouth > /dev/null
                        fi

                        # Remove existing rules for idempotency
                        echo "♻️ Removing existing rules if present..."
                        az network nsg rule delete --resource-group "$RG_NAME" --nsg-name "$NSG_NAME" --name AllowNodeExporter || true
                        # Removed the redundant rule deletion for AllowAppMetrics

                        # Add required rule
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
                            --destination-address-prefix '*' \
                            --destination-port-range 9100 \
                            --description "Allow Prometheus to scrape node metrics" > /dev/null

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
        
                            # ===== AZURE AUTH =====
                            echo "🔑 Authenticating to Azure..."
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID" --output none || {
                                echo "❌ Azure authentication failed"
                                exit 1
                            }
                            az account set --subscription "$ARM_SUBSCRIPTION_ID" --output none
        
                            # ===== DEPLOY NODE EXPORTER =====
                            echo "🚀 Deploying Node Exporter..."
                            NODE_EXPORTER_NAME="node-exporter-${BUILD_NUMBER}"
                            
                            # First check if container already exists
                            if az container show -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --query "name" -o tsv &>/dev/null; then
                                echo "⚠️ Node Exporter container already exists, deleting it..."
                                az container delete -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --yes --output none
                                sleep 30  # Wait for cleanup
                            fi
        
                            # Deploy with explicit DNS name label to help with IP assignment
                            echo "📦 Creating new Node Exporter instance..."
                            az container create \
                                --resource-group "$RESOURCE_GROUP" \
                                --name "$NODE_EXPORTER_NAME" \
                                --image prom/node-exporter:v1.6.1 \
                                --os-type Linux \
                                --cpu 1 --memory 1 \
                                --ports 9100 \
                                --ip-address Public \
                                --dns-name-label "node-exporter-${BUILD_NUMBER}" \
                                --location uksouth \
                                --command-line "--collector.disable-defaults --collector.cpu --collector.meminfo" \
                                --output none
        
                            echo "⏱️ Waiting for Node Exporter IP assignment..."
                            MAX_RETRIES=30  # Increased from 20
                            RETRY_DELAY=10  # Reduced from 15
                            NODE_EXPORTER_IP=""
                            
                            for ((i=1; i<=$MAX_RETRIES; i++)); do
                                NODE_EXPORTER_IP=$(az container show -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --query "ipAddress.ip" -o tsv)
                                if [ -n "$NODE_EXPORTER_IP" ]; then
                                    echo "✅ Node Exporter IP: $NODE_EXPORTER_IP"
                                    echo "NODE_EXPORTER_IP=$NODE_EXPORTER_IP" >> monitoring.env
                                    break
                                else
                                    echo "Attempt $i/$MAX_RETRIES: IP not yet assigned... Retrying in $RETRY_DELAY seconds."
                                    sleep $RETRY_DELAY
                                    
                                    # After 10 attempts, try to get more diagnostic info
                                    if [ $i -eq 10 ]; then
                                        echo "🔍 Gathering diagnostic information..."
                                        az container show -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --query "provisioningState" -o tsv
                                        az container show -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --query "instanceView.state" -o tsv
                                    fi
                                fi
                            done
        
                            if [ -z "$NODE_EXPORTER_IP" ]; then
                                echo "❌ ERROR: Node Exporter IP not assigned after $MAX_RETRIES attempts."
                                echo "⚠️ Checking container state..."
                                az container show -g "$RESOURCE_GROUP" -n "$NODE_EXPORTER_NAME" --output json
                                exit 1
                            fi
        
                            # ===== DEPLOY PROMETHEUS =====
                            echo "📊 Deploying Prometheus..."
                            PROMETHEUS_NAME="prometheus-${BUILD_NUMBER}"
                            
                            # Create Prometheus config file
                            cat <<EOF > prometheus-config.yml
                            global:
                              scrape_interval: 15s
                              evaluation_interval: 15s
        
                            scrape_configs:
                              - job_name: 'node-exporter'
                                static_configs:
                                  - targets: ['$NODE_EXPORTER_IP:9100']
                            EOF
        
                            az container create \
                                --resource-group "$RESOURCE_GROUP" \
                                --name "$PROMETHEUS_NAME" \
                                --image prom/prometheus:latest \
                                --os-type Linux \
                                --cpu 1 --memory 2 \
                                --ports 9090 \
                                --ip-address Public \
                                --dns-name-label "prometheus-${BUILD_NUMBER}" \
                                --location uksouth \
                                --command-line "--config.file=/etc/prometheus/prometheus.yml" \
                                --volumes prometheus-config.yml:/etc/prometheus/prometheus.yml \
                                --output none
        
                            echo "⏱️ Waiting for Prometheus IP assignment..."
                            PROMETHEUS_IP=""
                            for ((i=1; i<=15; i++)); do
                                PROMETHEUS_IP=$(az container show -g "$RESOURCE_GROUP" -n "$PROMETHEUS_NAME" --query "ipAddress.ip" -o tsv)
                                if [ -n "$PROMETHEUS_IP" ]; then
                                    echo "✅ Prometheus IP: $PROMETHEUS_IP"
                                    echo "PROMETHEUS_URL=http://$PROMETHEUS_IP:9090" >> monitoring.env
                                    break
                                else
                                    echo "Waiting for Prometheus IP... (attempt $i/15)"
                                    sleep 10
                                fi
                            done
        
                            if [ -z "$PROMETHEUS_IP" ]; then
                                echo "⚠️ WARNING: Prometheus IP not assigned, but continuing..."
                            fi
        
                            # ===== DEPLOY GRAFANA =====
                            echo "📈 Deploying Grafana..."
                            GRAFANA_NAME="grafana-${BUILD_NUMBER}"
                            
                            az container create \
                                --resource-group "$RESOURCE_GROUP" \
                                --name "$GRAFANA_NAME" \
                                --image grafana/grafana:latest \
                                --os-type Linux \
                                --cpu 1 --memory 2 \
                                --ports 3000 \
                                --ip-address Public \
                                --dns-name-label "grafana-${BUILD_NUMBER}" \
                                --location uksouth \
                                --environment-variables GF_SECURITY_ADMIN_PASSWORD="$GRAFANA_PASSWORD" \
                                --output none
        
                            echo "⏱️ Waiting for Grafana IP assignment..."
                            GRAFANA_IP=""
                            for ((i=1; i<=15; i++)); do
                                GRAFANA_IP=$(az container show -g "$RESOURCE_GROUP" -n "$GRAFANA_NAME" --query "ipAddress.ip" -o tsv)
                                if [ -n "$GRAFANA_IP" ]; then
                                    echo "✅ Grafana IP: $GRAFANA_IP"
                                    echo "GRAFANA_URL=http://$GRAFANA_IP:3000" >> monitoring.env
                                    break
                                else
                                    echo "Waiting for Grafana IP... (attempt $i/15)"
                                    sleep 10
                                fi
                            done
        
                            if [ -z "$GRAFANA_IP" ]; then
                                echo "⚠️ WARNING: Grafana IP not assigned, but continuing..."
                            fi
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
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID" > /dev/null
                            az account set --subscription "$ARM_SUBSCRIPTION_ID" > /dev/null
        
                            # ===== VERIFY IMAGE EXISTS =====
                            echo "🔍 Verifying Docker image exists..."
                            if ! docker login -u "$DOCKER_HUB_USER" -p "$DOCKER_HUB_PASSWORD" > /dev/null; then
                                echo "❌ ERROR: Failed to login to Docker Hub"
                                exit 1
                            fi
        
                            if ! docker pull ${IMAGE_TAG} > /dev/null; then
                                echo "❌ ERROR: Failed to pull image ${IMAGE_TAG}"
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
                                --cpu 1 --memory 2 \
                                --ports 8000 9100 \
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
                                --registry-password "$DOCKER_HUB_PASSWORD" > /dev/null
        
                            # ===== GET APPLICATION IP =====
                            echo "🔄 Getting application IP..."
                            MAX_RETRIES=10
                            RETRY_DELAY=10
                            APP_IP=""
                            
                            for ((i=1; i<=$MAX_RETRIES; i++)); do
                                APP_IP=$(az container show --resource-group MyPatientSurveyRG --name $ACI_NAME --query "ipAddress.ip" -o tsv)
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
                    // Load environment variables from file
                    def monitoringEnv = readFile('monitoring.env').trim()
                    def envVars = [:]
                    monitoringEnv.split('\n').each { line ->
                        def parts = line.split('=', 2)
                        if (parts.size() == 2) {
                            envVars[parts[0].trim()] = parts[1].trim()
                        }
                    }
        
                    // Check for required variables.
                    def requiredVars = ['PROMETHEUS_URL', 'GRAFANA_URL', 'APP_IP', 'NODE_EXPORTER_IP']
                    def missingVars = requiredVars.findAll { !envVars[it] }
                    
                    if (missingVars) {
                        error("Missing required monitoring environment variables: ${missingVars.join(', ')}")
                    }
        
                    // Pass the variables to the shell script
                    withEnv(envVars.collect { key, value -> "${key}=${value}" }) {
                        sh '''#!/bin/bash
                        set -eo pipefail
        
                        echo "📝 Configuring Prometheus..."
        
                        # Get Prometheus IP
                        PROMETHEUS_IP=$(echo "$PROMETHEUS_URL" | sed 's|http://||;s|:9090||')
        
                        # Create updated config
                        cat <<EOF > prometheus-config.yml
                        global:
                          scrape_interval: 15s
                          evaluation_interval: 15s
        
                        scrape_configs:
                          - job_name: 'node-exporter'
                            static_configs:
                              - targets: ['$NODE_EXPORTER_IP:9100']
                            params:
                              collect[]:
                                - cpu
                                - meminfo
                                - diskstats
                                - netdev
                                - filesystem
                                - loadavg
                                - bonding
                                - hwmon
                        EOF
        
                        # Reload Prometheus config
                        MAX_RETRIES=5
                        RETRY_DELAY=10
                        ATTEMPT=0
                        while [ $ATTEMPT -lt $MAX_RETRIES ]; do
                            echo "Reloading Prometheus (Attempt $((ATTEMPT+1))..."
                            if curl -X POST --max-time 10 --data-binary @prometheus-config.yml http://${PROMETHEUS_IP}:9090/-/reload; then
                                echo "✅ Prometheus reloaded successfully"
                                break
                            else
                                echo "⚠️ Attempt $((ATTEMPT+1)) failed"
                                ATTEMPT=$((ATTEMPT+1))
                                sleep $RETRY_DELAY
                            fi
                        done
        
                        if [ $ATTEMPT -eq $MAX_RETRIES ]; then
                            echo "❌ Failed to reload Prometheus after $MAX_RETRIES attempts"
                            exit 1
                        fi
        
                        echo "📊 Configuring Grafana datasource..."
                        GRAFANA_IP=$(echo "$GRAFANA_URL" | sed 's|http://||;s|:3000||')
        
                        # Add Prometheus as a datasource in Grafana
                        cat <<EOF > prometheus-datasource.json
                        {
                            "name": "Prometheus",
                            "type": "prometheus",
                            "url": "http://$PROMETHEUS_IP:9090",
                            "isDefault": true,
                            "access": "proxy"
                        }
                        EOF
        
                        # Use Grafana API to add the datasource
                        MAX_RETRIES=5
                        ATTEMPT=0
                        while [ $ATTEMPT -lt $MAX_RETRIES ]; do
                            echo "Adding Prometheus datasource to Grafana (Attempt $((ATTEMPT+1))..."
                            if curl -X POST --max-time 10 \
                                -H "Content-Type: application/json" \
                                -d @prometheus-datasource.json \
                                http://admin:$GRAFANA_PASSWORD@$GRAFANA_IP:3000/api/datasources; then
                                echo "✅ Grafana datasource configured successfully"
                                break
                            else
                                echo "⚠️ Attempt $((ATTEMPT+1)) failed"
                                ATTEMPT=$((ATTEMPT+1))
                                sleep $RETRY_DELAY
                            fi
                        done
        
                        if [ $ATTEMPT -eq $MAX_RETRIES ]; then
                            echo "❌ Failed to configure Grafana datasource after $MAX_RETRIES attempts"
                            exit 1
                        fi
                        '''
                    }
                }
            }
        }
        
        stage('Display Monitoring URLs') {
            steps {
                sh '''#!/bin/bash
                echo "========== MONITORING LINKS =========="
                source monitoring.env
                echo "Prometheus Dashboard: $PROMETHEUS_URL"
                echo "Grafana Dashboard: $GRAFANA_URL"
                echo "Node Metrics: http://$NODE_EXPORTER_IP:9100/metrics"
                echo "====================================="
                '''
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
