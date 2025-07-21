pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG  = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    // DB_HOST will be set dynamically by the Terraform stage
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }

  stages {
    stage('Checkout Code') {
      steps {
        checkout scm
      }
    }

    stage('Deploy Infrastructure (Terraform)') {
      steps {
        script {
          dir('infra/terraform') { // Correct path for Terraform files
            withCredentials([
              usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER_VAR', passwordVariable: 'DB_PASSWORD_VAR'),
              string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
              string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
              string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
              string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR') // Corrected variable name
            ])  {
              sh """
                # Export Azure credentials for Terraform
                export ARM_CLIENT_ID="${AZURE_CLIENT_ID}"
                export ARM_CLIENT_SECRET="${AZURE_CLIENT_SECRET}"
                export ARM_TENANT_ID="${AZURE_TENANT_ID}"
                export ARM_SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID_VAR}"

                # Export DB credentials for Terraform - these are sensitive variables for Terraform
                export DB_USER="${DB_USER_VAR}"
                export DB_PASSWORD="${DB_PASSWORD_VAR}"

                # Terraform commands
                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" -backend-config="storage_account_name=mypatientsurveytfstate" -backend-config="container_name=tfstate" -backend-config="key=patient_survey.tfstate"
                terraform plan -out=tfplan.out -var="db_user=\${DB_USER}" -var="db_password=\${DB_PASSWORD}"
                terraform apply -auto-approve tfplan.out
              """
              def sqlServerFqdn = sh(script: "terraform output -raw sql_server_fqdn", returnStdout: true).trim()
              env.DB_HOST = sqlServerFqdn
              echo "Database Host FQDN: ${env.DB_HOST}"
            }
          }
        }
      }
    }

    stage('Create .env File') {
      steps {
        dir('app') { // Assuming app files are in 'app/' directory
            withCredentials([
              usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
            ]) {
              sh '''
                echo "DB_HOST=${DB_HOST}" > .env
                echo "DB_USER=$DB_USER" >> .env
                echo "DB_PASSWORD=$DB_PASSWORD" >> .env
                echo "DB_NAME=${DB_NAME}" >> .env
              '''
            }
        }
      }
    }

    stage('Install Dependencies') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing ODBC Driver for SQL Server..."

          export DEBIAN_FRONTEND=noninteractive
          export TZ=Etc/UTC

          # Pre-seed license acceptance for msodbcsql17
          echo "msodbcsql17 msodbcsql/accept-eula boolean true" | sudo debconf-set-selections

          # 1. Install prerequisites for adding Microsoft repositories
          sudo apt-get update
          sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring

          # 2. Import the Microsoft GPG key
          curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

          # 3. Add the Microsoft SQL Server repository (adjust for your Ubuntu version if not 22.04)
          echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \
          | sudo tee /etc/apt/sources.list.d/mssql-release.list

          # 4. Update apt-get cache and install the ODBC driver
          sudo apt-get update
          sudo apt-get install -y msodbcsql17 unixodbc-dev

          echo "ODBC Driver installation complete."

          # Now, proceed with Python dependencies
          python3 --version
          pip3 install --upgrade pip
          pip install -r requirements.txt
        """
      }
    }

    stage('Security Scan') {
      steps {
        dir('app') { // Assuming app files are in 'app/' directory
          sh '''
            python3 -m pip install --user bandit pip-audit
            export PATH=$HOME/.local/bin:$PATH

            # static code analysis
            bandit -r app/ -lll

            # dependency audit (will fail on any vulnerabilities)
            pip-audit -r requirements.txt
          '''
        }
      }
    }

    stage('Run Tests') {
      steps {
        dir('app') { // Assuming tests are in tests/ within app/
          withCredentials([
            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
          ]) {
            sh '''
              export PATH=$HOME/.local/bin:$PATH
              export DB_USER=$DB_USER
              export DB_PASSWORD=$DB_PASSWORD
              python3 -m xmlrunner discover -s tests -o test-results
            '''
          }
        }
      }
    }

    stage('Build Docker Image') {
      steps {
        script {
          dir('app') { // Assuming Dockerfile is in 'app/' directory
            docker.build(IMAGE_TAG)
          }
        }
      }
    }

    stage('Container Scan') {
      steps {
        dir('app') { // Assuming the image context is from 'app/'
          sh """
            #!/usr/bin/env bash
            set -e
            # install trivy if missing
            if ! command -v trivy &>/dev/null; then
              curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \\
                | bash -s -- -b "\$HOME/.local/bin"
            fi
            export PATH="\$HOME/.local/bin:\$PATH"

            # now scan the image we just built
            trivy image --severity HIGH,CRITICAL ${IMAGE_TAG}
          """
        }
      }
    }

    stage('Push Docker Image') {
      steps {
        script {
          dir('app') { // Assuming context for Docker commands might still be in app/
            docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
              docker.image(IMAGE_TAG).push()
              docker.image(IMAGE_TAG).push('latest')
            }
          }
        }
      }
    }
  }

  post {
    always {
      junit 'app/test-results/*.xml' // Corrected path for JUnit reports
      cleanWs()
    }
  }
}
