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
                echo "Cleaning dpkg/apt locks..."
                for lock_file in /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock /var/cache/apt/archives/lock /var/lib/apt/lists/lock; do
                    [ -f "$lock_file" ] && sudo fuser -k "$lock_file" 2>/dev/null && sudo rm -f "$lock_file"
                done
                sudo dpkg --configure -a || true
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
        
                # Clean up problematic Grafana repo to avoid signature errors
                sudo rm -f /etc/apt/sources.list.d/grafana.list 2>/dev/null || true
                sudo rm -f /usr/share/keyrings/grafana.gpg 2>/dev/null || true
                
                # Microsoft SQL ODBC Driver repo with proper batch mode
                curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
                  | sudo gpg --dearmor --batch --yes -o /usr/share/keyrings/microsoft-prod.gpg
                echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \
                  | sudo tee /etc/apt/sources.list.d/mssql-release.list
        
                sudo apt-get update
                sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring python3-pip python3-venv
                yes | sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev
        
                pip3 install --upgrade pip
                pip3 install -r requirements.txt
                '''
            }
        }
        
        stage('Setup Grafana') {
            steps {
                sh '''
                #!/usr/bin/env bash
                set -e
                # Clean up any existing Grafana config
                sudo rm -f /etc/apt/sources.list.d/grafana.list
                sudo rm -f /usr/share/keyrings/grafana.gpg
                
                # Download and add Grafana key with batch mode
                curl -fsSL https://apt.grafana.com/gpg.key | sudo gpg --dearmor --batch --yes -o /usr/share/keyrings/grafana.gpg
                echo "deb [signed-by=/usr/share/keyrings/grafana.gpg] https://apt.grafana.com stable main" \
                  | sudo tee /etc/apt/sources.list.d/grafana.list
                
                sudo apt-get update
                '''
            }
        }
        stage('Install Terraform') {
            steps {
                sh '''
                set -e
                wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" \
                    | sudo tee /etc/apt/sources.list.d/hashicorp.list
                sudo apt-get update
                sudo apt-get install -y terraform
                terraform version
                '''
            }
        }

        stage('Install kubectl') {
            steps {
                sh '''
                set -e
                curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
                chmod +x kubectl
                mkdir -p "$WORKSPACE/bin"
                mv kubectl "$WORKSPACE/bin/kubectl"
                export PATH="$WORKSPACE/bin:$PATH"
                kubectl version --client --output=yaml
                '''
            }
        }
        stage('Deploy App Infrastructure') {
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
                            sh '''
                                set -e
        
                                export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
                                export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
                                export ARM_TENANT_ID="${AZURE_TENANT_ID}"
                                export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"
        
                                export TF_VAR_db_user="${DB_USER_TF}"
                                export TF_VAR_db_password="${DB_PASSWORD_TF}"
        
                                # Initialize Terraform
                                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \
                                               -backend-config="storage_account_name=mypatientsurveytfstate" \
                                               -backend-config="container_name=tfstate" \
                                               -backend-config="key=patient_survey.tfstate"
        
                                # Import existing resources if they exist
                                if ! terraform state list | grep -q azurerm_mssql_server.sql_server; then
                                  echo "Importing SQL Server..."
                                  terraform import -var="db_user=${TF_VAR_db_user}" \
                                                   -var="db_password=${TF_VAR_db_password}" \
                                                   azurerm_mssql_server.sql_server /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Sql/servers/survey-sql || echo "SQL Server not found, will create"
                                fi
        
                                if ! terraform state list | grep -q azurerm_mssql_database.main; then
                                  echo "Importing Database..."
                                  terraform import -var="db_user=${TF_VAR_db_user}" \
                                                   -var="db_password=${TF_VAR_db_password}" \
                                                   azurerm_mssql_database.main /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Sql/servers/survey-sql/databases/patient_survey_db || echo "Database not found, will create"
                                fi
        
                                if ! terraform state list | grep -q azurerm_mssql_firewall_rule.allow_azure_services; then
                                  echo "Importing Firewall Rule..."
                                  terraform import azurerm_mssql_firewall_rule.allow_azure_services /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Sql/servers/survey-sql/firewallRules/AllowAzureServices || echo "Firewall rule not found, will create"
                                fi
        
                                # Plan and apply app infrastructure
                                terraform plan -out=app_plan.out \
                                    -var="db_user=${TF_VAR_db_user}" \
                                    -var="db_password=${TF_VAR_db_password}" \
                                    -target="azurerm_mssql_server.sql_server" \
                                    -target="azurerm_mssql_database.main" \
                                    -target="azurerm_mssql_firewall_rule.allow_azure_services" \
                                    -target="azurerm_container_group.survey_app"
        
                                terraform apply -auto-approve app_plan.out
        
                                # Save DB info for downstream stages
                                echo "DB_HOST=$(terraform output -raw sql_server_fqdn)" > $WORKSPACE/monitoring.env
                                echo "DB_USER=${DB_USER_TF}" >> $WORKSPACE/monitoring.env
                                echo "DB_PASSWORD=${DB_PASSWORD_TF}" >> $WORKSPACE/monitoring.env
                            '''
                        }
                    }
                }
            }
        }
   
        stage('Deploy Monitoring Infrastructure') {
        steps {
            script {
                dir('infra/terraform') {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR'),
                        string(credentialsId: 'GRAFANA_PASSWORD', variable: 'GRAFANA_PASSWORD'),
                        usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER_TF', passwordVariable: 'DB_PASSWORD_TF')
                    ]) {
                        sh '''
                            export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
                            export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
                            export ARM_TENANT_ID="${AZURE_TENANT_ID}"
                            export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"
    
                            export TF_VAR_db_user="${DB_USER_TF}"
                            export TF_VAR_db_password="${DB_PASSWORD_TF}"
                            export TF_VAR_grafana_password="${GRAFANA_PASSWORD}"
    
                            terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \
                                           -backend-config="storage_account_name=mypatientsurveytfstate" \
                                           -backend-config="container_name=tfstate" \
                                           -backend-config="key=patient_survey.tfstate"
    
                            # Import Prometheus container group if missing
                            if ! terraform state list | grep -q azurerm_container_group.prometheus; then
                              echo "Importing Prometheus container group..."
                              terraform import -var="db_user=${TF_VAR_db_user}" -var="db_password=${TF_VAR_db_password}" \
                                  azurerm_container_group.prometheus \
                                  /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.ContainerInstance/containerGroups/prometheus-cg || echo "Prometheus not found, will create"
                            fi
    
                            # Import Grafana container group if missing
                            if ! terraform state list | grep -q azurerm_container_group.grafana; then
                              echo "Importing Grafana container group..."
                              terraform import -var="db_user=${TF_VAR_db_user}" -var="db_password=${TF_VAR_db_password}" \
                                  azurerm_container_group.grafana \
                                  /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.ContainerInstance/containerGroups/grafana-cg || echo "Grafana not found, will create"
                            fi
    
                            # Import storage account if missing
                            if ! terraform state list | grep -q azurerm_storage_account.monitoring; then
                              terraform import -var="db_user=${TF_VAR_db_user}" -var="db_password=${TF_VAR_db_password}" \
                                  azurerm_storage_account.monitoring \
                                  /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Storage/storageAccounts/monitoring || echo "Storage account not found, will create"
                            fi
    
                            # Import storage shares if missing
                            if ! terraform state list | grep -q azurerm_storage_share.prometheus; then
                              terraform import -var="db_user=${TF_VAR_db_user}" -var="db_password=${TF_VAR_db_password}" \
                                  azurerm_storage_share.prometheus \
                                  /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Storage/storageAccounts/monitoring/fileServices/default/shares/prometheus-data || echo "Prometheus share not found, will create"
                            fi
    
                            if ! terraform state list | grep -q azurerm_storage_share.grafana; then
                              terraform import -var="db_user=${TF_VAR_db_user}" -var="db_password=${TF_VAR_db_password}" \
                                  azurerm_storage_share.grafana \
                                  /subscriptions/${ARM_SUBSCRIPTION_ID}/resourceGroups/MyPatientSurveyRG/providers/Microsoft.Storage/storageAccounts/monitoring/fileServices/default/shares/grafana-data || echo "Grafana share not found, will create"
                            fi
    
                            # Plan and apply monitoring infrastructure safely
                            terraform plan -out=monitoring_plan.out \
                                -var="db_user=${TF_VAR_db_user}" \
                                -var="db_password=${TF_VAR_db_password}" \
                                -var="grafana_password=${TF_VAR_grafana_password}" \
                                -target="azurerm_container_group.prometheus" \
                                -target="azurerm_container_group.grafana" \
                                -target="azurerm_storage_account.monitoring" \
                                -target="azurerm_storage_share.prometheus" \
                                -target="azurerm_storage_share.grafana"
    
                            terraform apply -auto-approve monitoring_plan.out
    
                            # Save URLs and credentials to env file
                            echo "PROMETHEUS_URL=$(terraform output -raw prometheus_url)" > $WORKSPACE/monitoring.env
                            echo "GRAFANA_URL=$(terraform output -raw grafana_url)" >> $WORKSPACE/monitoring.env
                            echo "GRAFANA_CREDS=admin:${GRAFANA_PASSWORD}" >> $WORKSPACE/monitoring.env
                        '''
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
        
                        echo "✅ Container cleanup complete"
                        '''
                    }
                }
            }
        }

        stage('Create .env File') {
            steps {
                sh '''
                    source monitoring.env
                    echo "DB_HOST=$DB_HOST" > app/.env
                    echo "DB_USER=$DB_USER" >> app/.env
                    echo "DB_PASSWORD=$DB_PASSWORD" >> app/.env
                    echo "DB_NAME=$DB_NAME" >> app/.env

                    touch app/__init__.py
                    touch app/utils/__init__.py
                '''
            }
        }

        stage('Security Scan') {
            steps {
                dir('app') {
                    sh '''
                    set -ex
                    python3 -m pip install --user bandit pip-audit
                    export PATH="$HOME/.local/bin:$PATH"
                    bandit -r . -ll
                    pip-audit -r ../requirements.txt --verbose
                    '''
                }
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    export PATH=$HOME/.local/bin:$PATH
                    source monitoring.env
                    mkdir -p tests-results
                    touch tests/__init__.py
                    python3 -m xmlrunner discover -s tests -o test-results --failfast --verbose
                '''
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    withCredentials([usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                        docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
                            docker.build(IMAGE_TAG, '.').push()
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
                        usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'DOCKER_HUB_USER', passwordVariable: 'DOCKER_HUB_PASSWORD')
                    ]) {
                        sh '''
                        source monitoring.env
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
                        docker login -u "$DOCKER_HUB_USER" -p "$DOCKER_HUB_PASSWORD"
                        docker pull ${IMAGE_TAG}

                        az container create \
                            --resource-group MyPatientSurveyRG \
                            --name patientsurvey-app \
                            --image ${IMAGE_TAG} \
                            --os-type Linux \
                            --cpu 0.5 \
                            --memory 1.0 \
                            --ports 8001 9100 \
                            --ip-address Public \
                            --dns-name-label survey-app \
                            --restart-policy Always \
                            --environment-variables \
                                DB_HOST=$DB_HOST \
                                DB_USER=$DB_USER \
                                DB_PASSWORD=$DB_PASSWORD \
                                DB_NAME=$DB_NAME \
                            --registry-login-server index.docker.io \
                            --registry-username "$DOCKER_HUB_USER" \
                            --registry-password "$DOCKER_HUB_PASSWORD" || true
                        '''
                    }
                }
            }
        }

        stage('Configure Monitoring') {
            steps {
                script {
                    // Read monitoring environment variables
                    def envVars = readFile('monitoring.env').trim().split('\n').collectEntries { line ->
                        def (key, val) = line.split('=', 2)
                        [(key.trim()): val.trim()]
                    }
        
                    sh '''
                    set -eo pipefail
        
                    # Generate Prometheus config for the ACI
                    cat <<EOF > prometheus-config.yml
        global:
          scrape_interval: 15s
          evaluation_interval: 15s
        
        scrape_configs:
          - job_name: 'patient-survey-app'
            static_configs:
              - targets: ['${envVars['APP_DNS']}:8001']
        
          - job_name: 'myapp-node'
            static_configs:
              - targets: ['${envVars['APP_DNS']}:9100']
            metric_relabel_configs:
              - source_labels: [__name__]
                regex: '(node_cpu.*|node_memory.*|node_filesystem.*)'
                action: keep
        EOF
        
                    # Reload Prometheus
                    PROMETHEUS_IP=$(echo ${envVars['PROMETHEUS_URL']} | sed 's|http://||;s|:9090||')
                    curl -X POST --data-binary @prometheus-config.yml http://$PROMETHEUS_IP:9090/-/reload || echo "⚠️ Prometheus reload may need manual restart"
        
                    echo "✅ Prometheus configuration updated for ACI"
                    '''
                }
            }
        }


        stage('Display Monitoring URLs') {
            steps {
                sh '''
                    source monitoring.env
                    echo "========== MONITORING LINKS =========="
                    echo "Patient Survey App Metrics: http://survey-app.uksouth.azurecontainer.io:8001/metrics"
                    echo "Node Metrics: http://survey-app.uksouth.azurecontainer.io:9100/metrics"
                    echo "Prometheus Dashboard: $PROMETHEUS_URL"
                    echo "Grafana Dashboard: $GRAFANA_URL"
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
}
