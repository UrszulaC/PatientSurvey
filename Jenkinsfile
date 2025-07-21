// Define all credential IDs at the top for consistency
def AZURE_CREDENTIALS_ID = 'AZURE_CLIENT_ID'  // Name this whatever matches your Jenkins credentials
def DB_CREDENTIALS_ID = 'db-creds'
def AZURE_TENANT_ID_CREDENTIAL = 'AZURE_TENANT_ID'
def AZURE_SUBSCRIPTION_ID_CREDENTIAL = 'azure_subscription_id'

pipeline {
    agent any
    
    environment {
        DB_NAME = 'patient_survey_db'
        IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    }
    
    stages {
        // ... other stages remain the same until deployment ...

        stage('Deploy Infrastructure (Terraform)') {
            steps {
                script {
                    dir('infra/terraform') {
                        withCredentials([
                            usernamePassword(credentialsId: DB_CREDENTIALS_ID, 
                                          usernameVariable: 'DB_USER_TF', 
                                          passwordVariable: 'DB_PASSWORD_TF'),
                            string(credentialsId: AZURE_TENANT_ID_CREDENTIAL, 
                                  variable: 'AZURE_TENANT_ID'),
                            string(credentialsId: AZURE_SUBSCRIPTION_ID_CREDENTIAL, 
                                  variable: 'AZURE_SUBSCRIPTION_ID_VAR'),
                            usernamePassword(credentialsId: AZURE_CREDENTIALS_ID,
                                          usernameVariable: 'AZURE_CLIENT_ID',
                                          passwordVariable: 'AZURE_CLIENT_SECRET')
                        ]) {
                            sh """
                                export ARM_CLIENT_ID="$AZURE_CLIENT_ID"
                                export ARM_CLIENT_SECRET="$AZURE_CLIENT_SECRET"
                                export ARM_TENANT_ID="$AZURE_TENANT_ID"
                                export ARM_SUBSCRIPTION_ID="$AZURE_SUBSCRIPTION_ID_VAR"
                                export TF_VAR_db_user="$DB_USER_TF"
                                export TF_VAR_db_password="$DB_PASSWORD_TF"

                                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" \\
                                              -backend-config="storage_account_name=mypatientsurveytfstate" \\
                                              -backend-config="container_name=tfstate" \\
                                              -backend-config="key=patient_survey.tfstate"
                                terraform plan -out=tfplan.out
                                terraform apply -auto-approve tfplan.out
                            """
                            env.DB_HOST = sh(script: "terraform output -raw sql_server_fqdn", returnStdout: true).trim()
                            env.DB_USER = DB_USER_TF
                            env.DB_PASSWORD = DB_PASSWORD_TF
                        }
                    }
                }
            }
        }

        stage('Deploy Application (Azure Container Instances)') {
            steps {
                script {
                    withCredentials([
                        usernamePassword(credentialsId: AZURE_CREDENTIALS_ID,
                                      usernameVariable: 'AZURE_CLIENT_ID',
                                      passwordVariable: 'AZURE_CLIENT_SECRET'),
                        string(credentialsId: AZURE_TENANT_ID_CREDENTIAL, 
                             variable: 'AZURE_TENANT_ID'),
                        string(credentialsId: AZURE_SUBSCRIPTION_ID_CREDENTIAL,
                             variable: 'AZURE_SUBSCRIPTION_ID')
                    ]) {
                        sh """
                            set -e
                            echo "Logging into Azure..."
                            az login --service-principal -u "$AZURE_CLIENT_ID" -p "$AZURE_CLIENT_SECRET" --tenant "$AZURE_TENANT_ID"
                            az account set --subscription "$AZURE_SUBSCRIPTION_ID"

                            RESOURCE_GROUP_NAME="MyPatientSurveyRG"
                            ACI_NAME="patientsurvey-app-${env.BUILD_NUMBER}"
                            ACI_LOCATION="uksouth"

                            echo "Deploying Docker image ${env.IMAGE_TAG} to Azure Container Instances..."
                            az container create \\
                                --resource-group \$RESOURCE_GROUP_NAME \\
                                --name \$ACI_NAME \\
                                --image ${env.IMAGE_TAG} \\
                                --os-type Linux \\
                                --cpu 1 \\
                                --memory 1.5 \\
                                --restart-policy Always \\
                                --location \$ACI_LOCATION \\
                                --environment-variables DB_HOST=${env.DB_HOST} DB_USER=${env.DB_USER} DB_PASSWORD=${env.DB_PASSWORD} DB_NAME=${env.DB_NAME} \\
                                --no-wait

                            echo "Azure Container Instance deployment initiated."
                            az logout
                        """
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
    }
}
