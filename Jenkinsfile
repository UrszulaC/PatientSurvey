pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG  = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }
  stage('Install Dependencies') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing ODBC Driver for SQL Server..."

          export DEBIAN_FRONTEND=noninteractive
          export TZ=Etc/UTC

          # --- ADD THIS LINE TO PRE-SEED LICENSE ACCEPTANCE ---
          echo "msodbcsql17 msodbcsql/accept-eula boolean true" | sudo debconf-set-selections
          # --- END ADDITION ---

          # 1. Install prerequisites for adding Microsoft repositories
          sudo apt-get update
          sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring

          # 2. Import the Microsoft GPG key
          curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

          # 3. Add the Microsoft SQL Server repository
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
  
    stage('Create .env File') {
      steps {
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

    stage('Install Dependencies') {
      steps {
        sh """
          #!/usr/bin/env bash
          set -e

          echo "Installing ODBC Driver for SQL Server..."

          # --- ADD THESE LINES TO FORCE NON-INTERACTIVE MODE ---
          export DEBIAN_FRONTEND=noninteractive
          export TZ=Etc/UTC # Set a timezone to avoid prompts related to locale/timezone
          # --- END ADDITIONS ---

          # 1. Install prerequisites for adding Microsoft repositories
          sudo apt-get update
          sudo apt-get install -y apt-transport-https curl gnupg2 debian-archive-keyring

          # 2. Import the Microsoft GPG key
          curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | sudo gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg

          # 3. Add the Microsoft SQL Server repository
          echo "deb [arch=amd64,arm64,armhf signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/ubuntu/22.04/prod jammy main" \
          | sudo tee /etc/apt/sources.list.d/mssql-release.list

          # 4. Update apt-get cache and install the ODBC driver
          sudo apt-get update
          sudo apt-get install -y msodbcsql17 unixodbc-dev

          echo "ODBC Driver installation complete."

          # Python dependencies
          python3 --version
          pip3 install --upgrade pip
          pip install -r requirements.txt
        """
      }
    }
    stage('Security Scan') {
      steps {
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

    stage('Run Tests') {
      steps {
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
  stage('Build Docker Image') {
      steps {
        script {
          // will build e.g. urszulach/epa-feedback-app:66
          docker.build(IMAGE_TAG)
        }
      }
    }

    stage('Container Scan') {
      steps {
        // use a double-quoted Groovy string so ${IMAGE_TAG} is expanded before sending
        sh """
          #!/usr/bin/env bash
          set -e
          # install trivy if missing
          if ! command -v trivy &>/dev/null; then
            curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
              | bash -s -- -b "\$HOME/.local/bin"
          fi
          export PATH="\$HOME/.local/bin:\$PATH"

          # now scan the image we just built
          trivy image --severity HIGH,CRITICAL ${IMAGE_TAG}
        """
      }
    }

    stage('Push Docker Image') {
      steps {
        script {
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
      junit 'test-results/*.xml'
      cleanWs()
    }
  }
}

