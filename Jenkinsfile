pipeline {
  agent any

  environment {
    DB_HOST = '172.17.0.1'
    DB_NAME = 'patient_survey_db'
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }

  stages {
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
          // tag with build number and also "latest"
          IMAGE_TAG = "urszulach/epa-feedback-app:${env.BUILD_NUMBER}"
          docker.build(IMAGE_TAG)
        }
      }
    }

    stage('Container Scan') {
      steps {
        sh '''
          # install Trivy if missing
          if ! command -v trivy >/dev/null; then
            curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh | sh -s -- -b $HOME/.local/bin
          fi
          export PATH=$HOME/.local/bin:$PATH

          # scan just-built image for HIGH/Critical
          trivy image --severity HIGH,CRITICAL urszulach/epa-feedback-app:${env.BUILD_NUMBER}
        '''
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
      script {
        if (fileExists('test-results/results.xml')) {
          junit 'test-results/results.xml'
        } else {
          echo '⚠️ No test results found to publish.'
        }
      }
      cleanWs()
    }
  }
}
