pipeline {
    agent any
    environment {
        DB_NAME = 'patient_survey_db'
        IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
        PROMETHEUS_IMAGE_TAG = "urszulach/prometheus-custom:${env.BUILD_NUMBER}"
        DOCKER_REGISTRY = "index.docker.io"
        RESOURCE_GROUP = 'MyPatientSurveyRG'
        TF_STATE_STORAGE = 'mypatientsurveytfstate'
        TF_STATE_CONTAINER = 'tfstate'
        TF_STATE_KEY = 'patient_survey.tfstate'
    }

    options { timeout(time: 25, unit: 'MINUTES') }

    stages {
        stage('Clean Workspace') { steps { cleanWs() } }
        stage('Checkout Code') { steps { checkout scm } }

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
                # Terraform
                wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
                sudo apt-get update
                sudo apt-get install -y terraform
                terraform version
                # Azure CLI
                curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
                az version
                '''
            }
        }

        stage('Build Docker Images') {
            steps {
                script {
                    withCredentials([usernamePassword(credentialsId: 'docker-hub-creds', usernameVariable: 'DOCKER_USER', passwordVariable: 'DOCKER_PASS')]) {
                        // Build main app image
                        docker.build(IMAGE_TAG, '.').push()
                        // Build Prometheus image from infra/monitoring folder
                        dir('infra/monitoring') {
                            sh """
                            docker build -t ${PROMETHEUS_IMAGE_TAG} .
                            echo $DOCKER_PASS | docker login -u $DOCKER_USER --password-stdin
                            docker push ${PROMETHEUS_IMAGE_TAG}
                            """
                        }
                    }
                }
            }
        }

        stage('Initialize Terraform and Import Resources') {
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

                            terraform init -backend-config="resource_group_name=${RESOURCE_GROUP}" \
                                           -backend-config="storage_account_name=${TF_STATE_STORAGE}" \
                                           -backend-config="container_name=${TF_STATE_CONTAINER}" \
                                           -backend-config="key=${TF_STATE_KEY}"
                            '''
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
                            sh '''
                            set -e
        
                            # Export Azure service principal credentials for Terraform
                            export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
                            export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
                            export ARM_TENANT_ID="${ARM_TENANT_ID}"
                            export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"
        
                            # Plan and apply Terraform
                            terraform plan -out=complete_plan.out \
                                -var="db_user=${TF_VAR_db_user}" \
                                -var="db_password=${TF_VAR_db_password}" \
                                -var="grafana_password=${TF_VAR_grafana_password}" \
                                -var="prometheus_image_tag=${PROMETHEUS_IMAGE_TAG}" \
                                -var="resource_group_name=MyPatientSurveyRG" \
                                -var="location=uksouth" \
                                -var="docker_user=${TF_VAR_docker_user}" \
                                -var="docker_password=${TF_VAR_docker_password}"
        
                            terraform apply -auto-approve complete_plan.out
        
                            # Export outputs to monitoring.env
                            echo "DB_HOST=$(terraform output -raw sql_server_fqdn)" > $WORKSPACE/monitoring.env
                            echo "DB_USER=${TF_VAR_db_user}" >> $WORKSPACE/monitoring.env
                            echo "DB_PASSWORD=${TF_VAR_db_password}" >> $WORKSPACE/monitoring.env
                            echo "PROMETHEUS_URL=$(terraform output -raw prometheus_url)" >> $WORKSPACE/monitoring.env
                            echo "GRAFANA_URL=$(terraform output -raw grafana_url)" >> $WORKSPACE/monitoring.env
                            echo "GRAFANA_CREDS=admin:${TF_VAR_grafana_password}" >> $WORKSPACE/monitoring.env
        
                            echo "✅ Complete infrastructure applied successfully"
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
                export $(cat monitoring.env | xargs)
                echo "DB_HOST=$DB_HOST" > app/.env
                echo "DB_USER=$DB_USER" >> app/.env
                echo "DB_PASSWORD=$DB_PASSWORD" >> app/.env
                echo "DB_NAME=$DB_NAME" >> app/.env
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

        stage('Display Monitoring URLs') {
            steps {
                sh '''
                set -e
                source $WORKSPACE/monitoring.env
                echo "Patient Survey App Metrics: http://survey-app.uksouth.azurecontainer.io:8001/metrics"
                echo "Node Metrics: http://survey-app.uksouth.azurecontainer.io:9100/metrics"
                echo "Prometheus Dashboard: $PROMETHEUS_URL"
                echo "Grafana Dashboard: $GRAFANA_URL"
                '''
            }
        }
    }

    post { always { junit 'test-results/*.xml'; cleanWs() } }
}
