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
                            az container create \\
                                --resource-group MyPatientSurveyRG \\
                                --name "$NODE_EXPORTER_NAME" \\
                                --image prom/node-exporter:v1.6.1 \\
                                --os-type Linux \\
                                --cpu 1 --memory 1 \\
                                --ports 9100 \\
                                --ip-address Public \\
                                --location uksouth \\
                                --command-line "--collector.disable-defaults --collector.cpu --collector.meminfo" \\
                                --no-wait --output none
        
                            echo "⏱️ Waiting for Node Exporter IP assignment..."
                            MAX_RETRIES=20
                            RETRY_DELAY=15
                            NODE_EXPORTER_IP=""
                            
                            for ((i=1; i<=$MAX_RETRIES; i++)); do
                                NODE_EXPORTER_IP=$(az container show -g MyPatientSurveyRG -n "$NODE_EXPORTER_NAME" --query "ipAddress.ip" -o tsv)
                                if [ -n "$NODE_EXPORTER_IP" ]; then
                                    echo "✅ Node Exporter IP: $NODE_EXPORTER_IP"
                                    break
                                else
                                    echo "Attempt $i/$MAX_RETRIES: IP not yet assigned... Retrying in $RETRY_DELAY seconds."
                                    sleep $RETRY_DELAY
                                fi
                            done
        
                            if [ -z "$NODE_EXPORTER_IP" ]; then
                                echo "❌ ERROR: Node Exporter IP not assigned after $MAX_RETRIES attempts. Cannot continue."
                                exit 1
                            fi
        
                            # The rest of the script (Prometheus, Grafana deployment, etc.) remains the same.
                            # ...
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
