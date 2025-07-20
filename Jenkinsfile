pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG  = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
    // DB_HOST will be set dynamically by the Terraform stage
  }

  options {
    timeout(time: 20, unit: 'MIN')
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
              string(credentialsId: 'azure-subscription-id', variable: 'AZURE_SUBSCRIPTION_ID_VAR')
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

                # NEW: Create __init__.py files to make 'app' and 'tests' discoverable Python packages
                echo "Creating __init__.py files..."
                touch __init__.py # Makes 'app' a package
                # The tests/__init__.py will be handled by the Run Tests stage if tests/ is at root
                # If app/tests/ is also a package, you might need mkdir -p tests && touch tests/__init__.py here
                # but for now, assuming app/ is the only package under app/
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
        dir('app') { // Assuming app files are in 'app/' directory for Bandit scan context
          sh """
            #!/usr/bin/env bash
            set -ex # Added -x for debugging output, and -e for exiting on error

            echo "Installing security tools (bandit, pip-audit)..."
            # Added timeout to the pip install command for security tools
            timeout 5m python3 -m pip install --user bandit pip-audit
            echo "Security tools installed."

            export PATH=$HOME/.local/bin:$PATH
            echo "PATH updated: $PATH"

            echo "Running static code analysis with Bandit..."
            # Scan the current directory (which is 'app')
            bandit -r . -lll
            echo "Bandit scan complete."

            echo "Running dependency audit with pip-audit..."
            # pip-audit needs to find requirements.txt in the parent directory (workspace root)
            timeout 5m pip-audit -r ../requirements.txt --verbose
            echo "pip-audit complete."
          """
        }
      }
    }

    stage('Run Tests') {
      steps {
        // CRITICAL CHANGE: Removed dir('app') as tests are at repository root
        // Tests are in tests/test_survey.py at the repository root
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
          // CRITICAL FIX: Removed dir('app') - Dockerfile is at repository root
          docker.build(IMAGE_TAG, '.') // Explicitly set build context to current directory (repo root)
        }
      }
    }

    stage('Container Scan') {
      steps {
        // CRITICAL FIX: Removed dir('app') - Trivy operates on the image, not the Dockerfile context
        sh """
          #!/usr/bin/env bash
          set -ex # Added -x for debugging output, and -e for exiting on error

          echo "Installing Trivy..."
          # install trivy if missing, with a timeout
          if ! command -v trivy &>/dev/null; then
            timeout 5m curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \\
              | bash -s -- -b "\$HOME/.local/bin"
          fi
          echo "Trivy installed."

          export PATH="\$HOME/.local/bin:\$PATH"
          echo "PATH updated for Trivy: \$PATH"

          echo "Running container scan with Trivy..."
          # now scan the image we just built, with a timeout
          timeout 10m trivy image --severity HIGH,CRITICAL ${IMAGE_TAG}
          echo "Trivy scan complete."
        """
      }
    }

    stage('Push Docker Image') {
      steps {
        script {
          // CRITICAL FIX: Removed dir('app') - Docker push operates on the image tag
          docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
            docker.image(IMAGE_TAG).push()
            docker.image(IMAGE_TAG).push('latest')
          }
        }
      }
    }
  }

  post {
    always {
      junit 'test-results/*.xml' // Corrected path for JUnit reports
      cleanWs()
    }
  }
}
