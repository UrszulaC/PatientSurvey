pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG  = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    // DB_HOST will be set dynamically by the Terraform stage
  }

  options {
    // K4: Business value of DevOps (Time, Cost, Quality) - Timeout helps manage pipeline duration
    timeout(time: 20, unit: java.util.concurrent.TimeUnit.MINUTES)
  }

  stages {
    stage('Checkout Code') {
      steps {
        // K2: Principles of distributed Source Control (VCS polling is implicit in Jenkins setup)
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
              string(credentialsId: 'azure-subscription-id', variable: 'AZURE_SUBSCRIPTION_ID_VAR') // Corrected variable name
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

                # K7: Infrastructure-as-code (Terraform)
                # K12: Persistence/data layer deployment
                # S18: Specify cloud infrastructure in IaC DSL
                echo "Initializing Terraform..."
                terraform init -backend-config="resource_group_name=MyPatientSurveyRG" -backend-config="storage_account_name=mypatientsurveytfstate" -backend-config="container_name=tfstate" -backend-config="key=patient_survey.tfstate"
                echo "Planning Terraform changes..."
                terraform plan -out=tfplan.out -var="db_user=\${DB_USER}" -var="db_password=\${DB_PASSWORD}"
                echo "Applying Terraform changes..."
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
                # K7: General purpose programming (Python app uses .env)
                echo "DB_HOST=${DB_HOST}" > .env
                echo "DB_USER=$DB_USER" >> .env
                echo "DB_PASSWORD=$DB_PASSWORD" >> .env
                echo "DB_NAME=${DB_NAME}" >> .env

                # NEW: Create __init__.py files to make 'app' and 'tests' discoverable Python packages
                echo "Creating __init__.py files..."
                touch __init__.py # Makes 'app' a package
                # The tests/__init__.py will be handled by the Run Tests stage if tests/ is at root
                echo "__init__.py files created."
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

          # 1. Install prerequisites for adding Microsoft repositories
          sudo apt-get update
          sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring

          # 2. Import the Microsoft GPG key directly using tee
          curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo tee /usr/share/keyrings/microsoft-prod.gpg > /dev/null

          # 3. Add the Microsoft SQL Server repository (adjust for your Ubuntu version if not 22.04)
          echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \\
          | sudo tee /etc/apt/sources.list.d/mssql-release.list

          # 4. Update apt-get cache
          sudo apt-get update

          # CRITICAL CHANGE: Use ACCEPT_EULA=Y directly with the install command
          sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17 unixodbc-dev

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
        dir('app') { # Assuming app files are in 'app/' directory for Bandit scan context
          sh """
            #!/usr/bin/env bash
            set -ex # Added -x for debugging output, and -e for exiting on error

            # K5: Modern security tools (Bandit, Pip-audit)
            # S9: Application of cloud security tools into automated pipeline
            echo "Installing security tools (bandit, pip-audit)..."
            timeout 5m python3 -m pip install --user bandit pip-audit
            echo "Security tools installed."

            export PATH=$HOME/.local/bin:$PATH
            echo "PATH updated: $PATH"

            echo "Running static code analysis with Bandit..."
            bandit -r . -lll
            echo "Bandit scan complete."

            echo "Running dependency audit with pip-audit..."
            timeout 5m pip-audit -r ../requirements.txt --verbose
            echo "pip-audit complete."
          """
        }
      }
    }

    stage('Run Tests') {
      steps {
        // K14: Test Driven Development and Test Pyramid (Unit testing)
        // S14: Write tests and follow TDD discipline
        // S17: Code in a general-purpose programming language (Python tests)
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            export PATH=$HOME/.local/bin:$PATH
            export DB_USER=$DB_USER
            export DB_PASSWORD=$DB_PASSWORD
            # Ensure tests/ is a Python package for discovery
            mkdir -p tests # Ensure tests directory exists at root
            touch tests/__init__.py # Make 'tests' a package

            # Discover tests in the 'tests' directory at the workspace root
            python3 -m xmlrunner discover -s tests -o test-results
          '''
        }
      }
    }

    stage('Build Docker Image') {
      steps {
        script {
          // K8: Immutable infrastructure (Docker images)
          // K21: Architecture principles (Containerization)
          // S12: Automate tasks (Docker build)
          echo "Building Docker image ${IMAGE_TAG}..."
          docker.build(IMAGE_TAG, '.') // Explicitly set build context to current directory (repo root)
          echo "Docker image built successfully."
        }
      }
    }

    stage('Container Scan') {
      steps {
        // K5: Modern security tools (Trivy)
        // S9: Application of cloud security tools into automated pipeline
        sh """
          #!/usr/bin/env bash
          set -ex

          echo "Installing Trivy..."
          if ! command -v trivy &>/dev/null; then
            timeout 5m curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \\
              | bash -s -- -b "\$HOME/.local/bin"
          fi
          echo "Trivy installed."

          export PATH="\$HOME/.local/bin:\$PATH"
          echo "PATH updated for Trivy: \$PATH"

          echo "Running container scan with Trivy..."
          timeout 10m trivy image --severity HIGH,CRITICAL ${IMAGE_TAG}
          echo "Trivy scan complete."
        """
      }
    }

    stage('Push Docker Image') {
      steps {
        script {
          // K1: Continuous Integration (Build artifacts)
          // K15: Continuous Integration/Delivery/Deployment principles
          echo "Pushing Docker image ${IMAGE_TAG} to Docker Hub..."
          docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
            docker.image(IMAGE_TAG).push()
            docker.image(IMAGE_TAG).push('latest') // Optional: push as latest for easier pulling
          }
          echo "Docker image pushed successfully."
        }
      }
    }

    stage('Deploy Application (Azure Container Instances)') {
      steps {
        script {
          withCredentials([
            string(credentialsId: 'AZURE_CLIENT_ID', variable: 'AZURE_CLIENT_ID'),
            string(credentialsId: 'AZURE_CLIENT_SECRET', variable: 'AZURE_CLIENT_SECRET'),
            string(credentialsId: 'AZURE_TENANT_ID', variable: 'AZURE_TENANT_ID'),
            string(credentialsId: 'azure_subscription_id', variable: 'AZURE_SUBSCRIPTION_ID_VAR')
          ]) {
            // K15: Continuous Delivery/Deployment (Automated deployment)
            // K8: Immutable infrastructure (Deploying container image)
            // S5: Deploy immutable infrastructure
            // S12: Automate tasks (Azure CLI deployment)
            // Note: This deploys the console app in a container. For an API-based app,
            // the application code itself would need refactoring to expose an API.
            sh """
              echo "Logging into Azure..."
              az login --service-principal -u "${AZURE_CLIENT_ID}" -p "${AZURE_CLIENT_SECRET}" --tenant "${AZURE_TENANT_ID}"
              az account set --subscription "${AZURE_SUBSCRIPTION_ID_VAR}"

              RESOURCE_GROUP_NAME="MyPatientSurveyRG" # Assuming this RG is managed by Terraform
              ACI_NAME="patientsurvey-app-${env.BUILD_NUMBER}"
              ACI_LOCATION="uksouth" # Adjust as per your Azure region

              echo "Deploying Docker image ${IMAGE_TAG} to Azure Container Instances..."

              az container create \\
                --resource-group \$RESOURCE_GROUP_NAME \\
                --name \$ACI_NAME \\
                --image ${IMAGE_TAG} \\
                --os-type Linux \\
                --cpu 1 \\
                --memory 1.5 \\
                --restart-policy Always \\
                --location \$ACI_LOCATION \\
                --environment-variables DB_HOST=${DB_HOST} DB_USER=${DB_USER} DB_PASSWORD=${DB_PASSWORD} DB_NAME=${DB_NAME} \\
                --no-wait # Do not wait for deployment to complete to speed up pipeline

              echo "Azure Container Instance deployment initiated. Check Azure portal for status."

              echo "Logging out of Azure..."
              az logout
            """
          }
        }
      }
    }
  }

  post {
    always {
      // K1: Continuous Integration (Ensuring all tests pass)
      junit 'test-results/*.xml' // Corrected path for JUnit reports
      cleanWs()
    }
  }
}
