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
                        sh """
                        #!/bin/bash
                        set -e
        
                        # Generate valid container names
                        PROMETHEUS_NAME="prometheus-\${BUILD_NUMBER}"
                        GRAFANA_NAME="grafana-\${BUILD_NUMBER}"
        
                        echo "=== Deploying Monitoring Stack ==="
                        az login --service-principal -u \$ARM_CLIENT_ID -p \$ARM_CLIENT_SECRET --tenant \$ARM_TENANT_ID
                        az account set --subscription \$ARM_SUBSCRIPTION_ID
        
                        # Cleanup previous deployments
                        echo "Cleaning up previous containers..."
                        az container delete --resource-group MyPatientSurveyRG --name \$PROMETHEUS_NAME --yes || true
                        az container delete --resource-group MyPatientSurveyRG --name \$GRAFANA_NAME --yes || true
        
                        # ===== PROMETHEUS DEPLOYMENT =====
                        echo "Deploying Prometheus..."
                        PROMETHEUS_CONFIG_BASE64=\$(base64 -w0 infra/monitoring/prometheus.yml)
                        az container create \\
                          --resource-group MyPatientSurveyRG \\
                          --name \$PROMETHEUS_NAME \\
                          --image prom/prometheus:v2.47.0 \\
                          --os-type Linux \\
                          --cpu 1 \\
                          --memory 2 \\
                          --ports 9090 \\
                          --ip-address Public \\
                          --command-line "/bin/prometheus --config.file=/etc/prometheus/prometheus.yml --storage.tsdb.path=/prometheus --web.enable-lifecycle --web.enable-admin-api" \\
                          --environment-variables \\
                            PROMETHEUS_WEB_LISTEN_ADDRESS=0.0.0.0:9090
        
                        # Verify running state
                        az container show \\
                          --resource-group MyPatientSurveyRG \\
                          --name \$PROMETHEUS_NAME \\
                          --query "containers[0].instanceView.currentState.state" \\
                          -o tsv | grep -q "Running" || exit 1
        
                        # ===== GRAFANA DEPLOYMENT =====
                        echo "Deploying Grafana with default config..."
                        az container create \\
                            --resource-group MyPatientSurveyRG \\
                            --name \$GRAFANA_NAME \\
                            --image grafana/grafana:9.5.6 \\
                            --os-type Linux \\
                            --cpu 1 \\
                            --memory 2 \\
                            --ports 3000 \\
                            --ip-address Public \\
                            --dns-name-label \$GRAFANA_NAME \\
                            --location uksouth \\
                            --environment-variables \\
                                GF_SECURITY_ADMIN_USER=admin \\
                                GF_SECURITY_ADMIN_PASSWORD=\$GRAFANA_PASSWORD \\
                            --no-wait
        
                        # ===== WAIT FOR DEPLOYMENTS =====
                        echo "Waiting for deployments to complete (max 5 minutes)..."
                        for i in {1..30}; do
                            PROM_STATUS=\$(az container show -g MyPatientSurveyRG -n \$PROMETHEUS_NAME --query "provisioningState" -o tsv)
                            GRAFANA_STATUS=\$(az container show -g MyPatientSurveyRG -n \$GRAFANA_NAME --query "provisioningState" -o tsv)
                            
                            if [[ "\$PROM_STATUS" == "Succeeded" && "\$GRAFANA_STATUS" == "Succeeded" ]]; then
                                break
                            fi
                            sleep 10
                        done
        
                        # ===== VERIFY DEPLOYMENTS =====
                        PROMETHEUS_FQDN=\$(az container show -g MyPatientSurveyRG -n \$PROMETHEUS_NAME --query "ipAddress.fqdn" -o tsv)
                        GRAFANA_FQDN=\$(az container show -g MyPatientSurveyRG -n \$GRAFANA_NAME --query "ipAddress.fqdn" -o tsv)
        
                        # ===== CONFIGURE GRAFANA =====
                        echo "Configuring Grafana data source..."
                        curl --retry 3 --retry-delay 5 --max-time 10 -X POST \\
                            "http://admin:\$GRAFANA_PASSWORD@\$GRAFANA_FQDN:3000/api/datasources" \\
                            -H "Content-Type: application/json" \\
                            -d '{"name":"Prometheus","type":"prometheus","url":"http://'\$PROMETHEUS_FQDN':9090","access":"proxy"}' \\
                            || echo "Warning: Grafana datasource configuration failed (may already exist)"
        
                        # ===== OUTPUT RESULTS =====
                        echo "PROMETHEUS_URL=http://\$PROMETHEUS_FQDN:9090" > monitoring.env
                        echo "GRAFANA_URL=http://\$GRAFANA_FQDN:3000" >> monitoring.env
                        echo "GRAFANA_CREDS=admin:\$GRAFANA_PASSWORD" >> monitoring.env
        
                        echo "=== Monitoring Deployment Complete ==="
                        echo "Prometheus: http://\$PROMETHEUS_FQDN:9090"
                        echo "Grafana: http://\$GRAFANA_FQDN:3000 (admin/\$GRAFANA_PASSWORD)"
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
    
