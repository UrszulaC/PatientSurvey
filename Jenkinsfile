pipeline {
  agent any

  environment {
    DB_NAME = 'patient_survey_db'
    IMAGE_TAG  = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }

  stages {
    stage('Deploy Infrastructure (Terraform)') {
      steps {
        script {
          withCredentials([
            usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER_VAR', passwordVariable: 'DB_PASSWORD_VAR')
          ]) {
            sh """
              terraform init -backend-config="resource_group_name=MyPatientSurveyRG" -backend-config="storage_account_name=mypatientsurveytfstate" -backend-config="container_name=tfstate" -backend-config="key=patient_survey.tfstate"
              terraform plan -out=tfplan.out -var="db_user=${DB_USER_VAR}" -var="db_password=${DB_PASSWORD_VAR}"
              terraform apply -auto-approve tfplan.out
            """
            // Capture the FQDN output from Terraform and set it as a Jenkins environment variable
            def sqlServerFqdn = sh(script: "terraform output -raw sql_server_fqdn", returnStdout: true).trim()
            env.DB_HOST = sqlServerFqdn // <-- THIS IS WHERE DB_HOST IS NOW SET
            echo "Database Host FQDN: ${env.DB_HOST}"
          }
        }
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
        sh '''
          python3 --version
          pip3 install --upgrade pip
          pip install -r requirements.txt
        '''
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

