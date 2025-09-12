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
            steps { cleanWs() }
        }

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

        stage('Install Terraform') {
            steps {
                sh '''
                set -e
                wget -O- https://apt.releases.hashicorp.com/gpg | gpg --dearmor | sudo tee /usr/share/keyrings/hashicorp-archive-keyring.gpg > /dev/null
                echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
                sudo apt-get update
                sudo apt-get install -y terraform
                terraform version
                '''
            }
        }

        stage('Deploy App Infrastructure') {
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

                                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \
                                               -backend-config="storage_account_name=mypatientsurveytfstate" \
                                               -backend-config="container_name=tfstate" \
                                               -backend-config="key=patient_survey.tfstate"

                                terraform plan -out=app_plan.out \
                                    -var="db_user=${TF_VAR_db_user}" \
                                    -var="db_password=${TF_VAR_db_password}" \
                                    -var="grafana_password=${TF_VAR_grafana_password}"

                                terraform apply -auto-approve app_plan.out

                                echo "DB_HOST=$(terraform output -raw sql_server_fqdn)" > $WORKSPACE/monitoring.env
                                echo "DB_USER=${TF_VAR_db_user}" >> $WORKSPACE/monitoring.env
                                echo "DB_PASSWORD=${TF_VAR_db_password}" >> $WORKSPACE/monitoring.env
                                echo "✅ App infrastructure applied successfully"
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
                            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'ARM_CLIENT_ID'),
                            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'ARM_CLIENT_SECRET'),
                            string(credentialsId: 'AZURE_TENANT_ID', variable: 'ARM_TENANT_ID'),
                            string(credentialsId: 'azure_subscription_id', variable: 'ARM_SUBSCRIPTION_ID_VAR'),
                            string(credentialsId: 'GRAFANA_PASSWORD', variable: 'TF_VAR_grafana_password'),
                            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'TF_VAR_db_user', passwordVariable: 'TF_VAR_db_password')
                        ]) {
                            sh '''
                                set -e
                                export ARM_CLIENT_ID="${ARM_CLIENT_ID}"
                                export ARM_CLIENT_SECRET="${ARM_CLIENT_SECRET}"
                                export ARM_TENANT_ID="${ARM_TENANT_ID}"
                                export ARM_SUBSCRIPTION_ID="${ARM_SUBSCRIPTION_ID_VAR}"

                                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \
                                               -backend-config="storage_account_name=mypatientsurveytfstate" \
                                               -backend-config="container_name=tfstate" \
                                               -backend-config="key=patient_survey.tfstate"

                                terraform plan -out=monitoring_plan.out \
                                    -var="db_user=${TF_VAR_db_user}" \
                                    -var="db_password=${TF_VAR_db_password}" \
                                    -var="grafana_password=${TF_VAR_grafana_password}"

                                terraform apply -auto-approve monitoring_plan.out

                                echo "PROMETHEUS_URL=$(terraform output -raw prometheus_url)" >> $WORKSPACE/monitoring.env
                                echo "GRAFANA_URL=$(terraform output -raw grafana_url)" >> $WORKSPACE/monitoring.env
                                echo "GRAFANA_CREDS=admin:${TF_VAR_grafana_password}" >> $WORKSPACE/monitoring.env
                                echo "✅ Monitoring infrastructure applied successfully"
                            '''
                        }
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
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
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
                            --resource-group $RESOURCE_GROUP \
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

        stage('Display Monitoring URLs') {
            steps {
                sh '''
                    source monitoring.env
                    echo "Patient Survey App Metrics: http://survey-app.uksouth.azurecontainer.io:8001/metrics"
                    echo "Node Metrics: http://survey-app.uksouth.azurecontainer.io:9100/metrics"
                    echo "Prometheus Dashboard: $PROMETHEUS_URL"
                    echo "Grafana Dashboard: $GRAFANA_URL"
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
