pipeline {
    agent any
    environment {
        DB_NAME = 'patient_survey_db'
        IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
        DOCKER_REGISTRY = "index.docker.io"
        RESOURCE_GROUP = 'MyPatientSurveyRG' 
        TF_STATE_STORAGE = 'mypatientsurveytfstate'
        TF_STATE_CONTAINER = 'tfstate'
        TF_STATE_KEY = 'patient_survey.tfstate'
    }

    options {
        timeout(time: 25, unit: 'MINUTES')
    }

    stages {
        stage('Clean Workspace') {
            steps { cleanWs() }
        }

        stage('Checkout Code') { 
            steps { 
                checkout scm 
            } 
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                set -e
                sudo apt-get update
                sudo apt-get install -y apt-transport-https curl gnupg2 python3-pip python3-venv
                pip3 install --upgrade pip
                pip3 install -r requirements.txt
                '''
            }
        }

        stage('Install Terraform and Azure CLI') {
            steps {
                sh '''
                set -e
                # Install Terraform
                wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
                sudo apt-get update
                sudo apt-get install -y terraform
                terraform version
                
                # Install Azure CLI
                curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
                az version
                '''
            }
        }

        stage('Initialize Terraform and Import Existing Resources') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'TF_VAR_db_user', passwordVariable: 'TF_VAR_db_password'),
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID_VAR'),
                            string(credentialsId: 'GRAFANA_PASSWORD', variable: 'TF_VAR_grafana_password')
                        ]) {
                            sh '''
                                set -e
                                export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
                                export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
                                export ARM_TENANT_ID="${ARM_TENANT_ID}"
                                export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"
                                
                                export TF_VAR_client_id="${ARM_CLIENT_ID}"
                                export TF_VAR_client_secret="${ARM_CLIENT_SECRET}"
                                export TF_VAR_tenant_id="${ARM_TENANT_ID}"
                                export TF_VAR_subscription_id="${ARM_SUBSCRIPTION_ID_VAR}"
        
                                # Initialize Terraform with backend
                                terraform init -backend-config="resource_group_name=${RESOURCE_GROUP}" \
                                               -backend-config="storage_account_name=${TF_STATE_STORAGE}" \
                                               -backend-config="container_name=${TF_STATE_CONTAINER}" \
                                               -backend-config="key=${TF_STATE_KEY}"
        
                                # Login to Azure for resource import
                                az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                                az account set --subscription "$ARM_SUBSCRIPTION_ID_VAR"
        
                                # Get current state
                                terraform state list > existing_state.txt || true
                                
                                # Function to import resource if not in state
                                import_if_missing() {
                                    local resource_name="$1"
                                    local azure_resource_id="$2"
                                    
                                    if ! grep -xq "$resource_name" existing_state.txt; then
                                        echo "Attempting to import $resource_name..."
                                        if terraform import -var="resource_group_name=MyPatientSurveyRG" -var="location=uksouth" "$resource_name" "$azure_resource_id" 2>/dev/null; then
                                            echo "✅ Successfully imported $resource_name"
                                        else
                                            echo "⚠️  Import failed for $resource_name (resource may not exist or ID format may be different)"
                                        fi
                                    else
                                        echo "✅ $resource_name already in state"
                                    fi
                                }
        
                                # Import SQL resources
                                import_if_missing "azurerm_mssql_server.sql_server" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Sql/servers/patientsurveysql"
                                import_if_missing "azurerm_mssql_database.sql_database" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Sql/servers/patientsurveysql/databases/patient_survey_db"
                                import_if_missing "azurerm_mssql_firewall_rule.allow_azure_services" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Sql/servers/patientsurveysql/firewallRules/AllowAzureServices"
                                
                                # Import Network resources
                                import_if_missing "azurerm_network_security_group.monitoring_nsg" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Network/networkSecurityGroups/monitoring-nsg"
                                
                                # Import Storage Account
                                import_if_missing "azurerm_storage_account.monitoring" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/mypatientsurveymonitor"
                                
                                # Import Storage Shares
                                import_if_missing "azurerm_storage_share.prometheus" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/mypatientsurveymonitor/fileServices/default/shares/prometheus-data"    
                                import_if_missing "azurerm_storage_share.grafana" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/mypatientsurveymonitor/fileServices/default/shares/grafana-data"

        
                                # Try to import container groups if they exist
                                import_if_missing "azurerm_container_group.prometheus" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ContainerInstance/containerGroups/prometheus-cg"
                                import_if_missing "azurerm_container_group.grafana" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.ContainerInstance/containerGroups/grafana-cg"
        
                                echo "✅ Terraform initialization and resource import completed"
                            '''
                        }
                    }
                }
            }
        }
        stage('Import Existing Resources if Missing') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID_VAR')
                        ]) {
                            sh '''
                                set -e
                                export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
                                export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
                                export ARM_TENANT_ID="${ARM_TENANT_ID}"
                                export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"
        
                                az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                                az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                                terraform init -backend-config="resource_group_name=${RESOURCE_GROUP}" \
                                               -backend-config="storage_account_name=${TF_STATE_STORAGE}" \
                                               -backend-config="container_name=${TF_STATE_CONTAINER}" \
                                               -backend-config="key=${TF_STATE_KEY}"
        
                                terraform state list > existing_state.txt || true
        
                                import_if_missing() {
                                    local resource_name="$1"
                                    local azure_resource_id="$2"
        
                                    if ! grep -xq "$resource_name" existing_state.txt; then
                                        echo "Attempting to import $resource_name..."
                                        terraform import "$resource_name" "$azure_resource_id" && \
                                        echo "✅ Imported $resource_name" || \
                                        echo "⚠️ Failed to import $resource_name"
                                    else
                                        echo "✅ $resource_name already in state"
                                    fi
                                }
        
                                # Conditional import of resources
                                import_if_missing "azurerm_mssql_server.sql_server" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Sql/servers/patientsurveysql"
                                import_if_missing "azurerm_network_security_group.monitoring_nsg" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Network/networkSecurityGroups/monitoring-nsg"
                                import_if_missing "azurerm_storage_account.monitoring" "/subscriptions/${ARM_SUBSCRIPTION_ID_VAR}/resourceGroups/${RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/mypatientsurveymonitor"
        
                                echo "✅ Conditional import stage completed"
                            '''
                        }
                    }
                }
            }
        }
       
       stage('Build Docker Images') {
            steps {
                script {
                    withCredentials([usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                        docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
                            
                            // ✅ Build Python app image (Dockerfile is in project root)
                            docker.build("urszulach/epa-feedback-app:${env.BUILD_NUMBER}", ".").push()
        
                            // ✅ Build Prometheus image (inside infra/monitoring)
                            dir('infra/monitoring') {
                                docker.build("urszulach/prometheus-custom:${env.BUILD_NUMBER}", ".").push()
                            }
                        }
                    }
                }
            }
        }

        stage('Deploy Complete Infrastructure') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'TF_VAR_db_user', passwordVariable: 'TF_VAR_db_password'),
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID_VAR'),
                            string(credentialsId: 'GRAFANA_PASSWORD', variable: 'TF_VAR_grafana_password'),
                            usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'TF_VAR_docker_user', passwordVariable: 'TF_VAR_docker_password')
                        ]) {
                            sh '''#!/bin/bash
        set -e
        
        export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
        export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
        export ARM_TENANT_ID="${ARM_TENANT_ID}"
        export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"
        
        export TF_VAR_client_id="${ARM_CLIENT_ID}"
        export TF_VAR_client_secret="${ARM_CLIENT_SECRET}"
        export TF_VAR_tenant_id="${ARM_TENANT_ID}"
        export TF_VAR_subscription_id="${ARM_SUBSCRIPTION_ID_VAR}"
        
        # Initialize Terraform with backend
        terraform init -backend-config="resource_group_name=${RESOURCE_GROUP}" \
                       -backend-config="storage_account_name=${TF_STATE_STORAGE}" \
                       -backend-config="container_name=${TF_STATE_CONTAINER}" \
                       -backend-config="key=${TF_STATE_KEY}"
        
        # Terraform plan with all required variables
        terraform plan -out=complete_plan.out \
            -var="db_user=${TF_VAR_db_user}" \
            -var="db_password=${TF_VAR_db_password}" \
            -var="grafana_password=${TF_VAR_grafana_password}" \
            -var="docker_user=${TF_VAR_docker_user}" \
            -var="docker_password=${TF_VAR_docker_password}" \
            -var="prometheus_image_tag=${BUILD_NUMBER}" \
            -var="resource_group_name=MyPatientSurveyRG" \
            -var="location=uksouth"
        
        # Apply plan
        terraform apply -auto-approve complete_plan.out
        
        # Export outputs to monitoring.env
        echo "DB_HOST=$(terraform output -raw sql_server_fqdn)" > "$WORKSPACE/monitoring.env"
        echo "DB_USER=${TF_VAR_db_user}" >> "$WORKSPACE/monitoring.env"
        echo "DB_PASSWORD=${TF_VAR_db_password}" >> "$WORKSPACE/monitoring.env"
        echo "PROMETHEUS_URL=$(terraform output -raw prometheus_url)" >> "$WORKSPACE/monitoring.env"
        echo "GRAFANA_URL=$(terraform output -raw grafana_url)" >> "$WORKSPACE/monitoring.env"
        echo "GRAFANA_CREDS=admin:${TF_VAR_grafana_password}" >> "$WORKSPACE/monitoring.env"
        
        echo "✅ Complete infrastructure applied successfully"
        '''
                        }
                    }
                }
            }
        }

        stage('Replace Survey App Container Group') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'TF_VAR_db_user', passwordVariable: 'TF_VAR_db_password'),
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID_VAR'),
                            string(credentialsId: 'GRAFANA_PASSWORD', variable: 'TF_VAR_grafana_password'),
                            usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'TF_VAR_docker_user', passwordVariable: 'TF_VAR_docker_password')
                        ]) {
                            sh '''#!/bin/bash
                            set -e
                            
                            export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
                            export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
                            export ARM_TENANT_ID="${ARM_TENANT_ID}"
                            export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"
                            
                            export TF_VAR_client_id="${ARM_CLIENT_ID}"
                            export TF_VAR_client_secret="${ARM_CLIENT_SECRET}"
                            export TF_VAR_tenant_id="${ARM_TENANT_ID}"
                            export TF_VAR_subscription_id="${ARM_SUBSCRIPTION_ID_VAR}"
                            
                            # Initialize Terraform (if not already done)
                            terraform init -backend-config="resource_group_name=${RESOURCE_GROUP}" \
                                           -backend-config="storage_account_name=${TF_STATE_STORAGE}" \
                                           -backend-config="container_name=${TF_STATE_CONTAINER}" \
                                           -backend-config="key=${TF_STATE_KEY}"
                            
                            # Replace ONLY the survey app container group
                            terraform apply -replace="azurerm_container_group.survey_app" -auto-approve \
                                -var="db_user=${TF_VAR_db_user}" \
                                -var="db_password=${TF_VAR_db_password}" \
                                -var="grafana_password=${TF_VAR_grafana_password}" \
                                -var="docker_user=${TF_VAR_docker_user}" \
                                -var="docker_password=${TF_VAR_docker_password}" \
                                -var="prometheus_image_tag=${BUILD_NUMBER}" \
                                -var="resource_group_name=MyPatientSurveyRG" \
                                -var="location=uksouth"
                            
                            echo "✅ Survey app container group replaced successfully"
                            '''
                        }
                    }
                }
            }
        }
        stage('Create .env File') {
            steps {
                sh '''
                    set -e
                    # Read values without exporting them (avoids printing secrets)
                    DB_HOST=$(grep ^DB_HOST monitoring.env | cut -d '=' -f2-)
                    DB_USER=$(grep ^DB_USER monitoring.env | cut -d '=' -f2-)
                    DB_PASSWORD=$(grep ^DB_PASSWORD monitoring.env | cut -d '=' -f2-)
                    DB_NAME=$(grep ^DB_NAME monitoring.env | cut -d '=' -f2-)
        
                    # Write .env file
                    cat > app/.env <<EOL
        DB_HOST=$DB_HOST
        DB_USER=$DB_USER
        DB_PASSWORD=$DB_PASSWORD
        DB_NAME=$DB_NAME
        EOL
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    mkdir -p test-results
                    touch tests/__init__.py
                    python3 -m xmlrunner discover -s tests -o test-results --failfast --verbose
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
                        
                        # Run Bandit for Python security analysis
                        bandit -r . -ll
                        
                        # Run pip-audit for dependency vulnerabilities
                        pip-audit -r ../requirements.txt --verbose
                    '''
                }
            }
        }
        stage('Cleanup Old Container') {
            steps {
                script {
                    withCredentials([
                        string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                        string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                        string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                        string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID')
                    ]) {
                        sh '''
                            set -e
                            az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                            az account set --subscription "$ARM_SUBSCRIPTION_ID"

                            if az container show --resource-group $RESOURCE_GROUP --name survey-app-cg &>/dev/null; then
                                echo "Deleting old container survey-app-cg..."
                                az container delete --resource-group $RESOURCE_GROUP --name survey-app-cg --yes
                            else
                                echo "No old container to delete."
                            fi
                        '''
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
                        set -e
                        # Load env vars
                        export $(grep -v "^#" monitoring.env | xargs)
        
                        az login --service-principal -u "$ARM_CLIENT_ID" -p "$ARM_CLIENT_SECRET" --tenant "$ARM_TENANT_ID"
                        az account set --subscription "$ARM_SUBSCRIPTION_ID"
        
                        docker login -u "$DOCKER_HUB_USER" -p "$DOCKER_HUB_PASSWORD"
                        docker pull ${IMAGE_TAG}
        
                        # Check if container exists
                        if az container show --resource-group $RESOURCE_GROUP --name survey-app-cg --query name -o tsv 2>/dev/null; then
                            echo "Container exists — deleting..."
                            az container delete --resource-group $RESOURCE_GROUP --name survey-app-cg --yes
                        fi
        
                        echo "Creating new container..."
                        az container create \
                            --resource-group $RESOURCE_GROUP \
                            --name survey-app-cg \
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
                            --registry-password "$DOCKER_HUB_PASSWORD"
                        '''
                    }
                }
            }
        }

       stage('Display Monitoring URLs') {
            steps {
                sh '''
                    set -e
                    # Load environment variables
                    export $(grep -v "^#" monitoring.env | xargs)
        
                    echo "Patient Survey App Metrics: http://survey-app.uksouth.azurecontainer.io:8001/metrics"
                    echo "Node Metrics: http://survey-app.uksouth.azurecontainer.io:9100/metrics"
                    echo "Prometheus Dashboard: $PROMETHEUS_URL"
                    echo "Grafana Dashboard: $GRAFANA_URL"
                    echo "⚠️ Grafana credentials are hidden for security"
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
