pipeline {
  agent {
    docker {
      image 'python:3.10'
      args '-u root'
    }
  }

  environment {
    DB_HOST = 'host.docker.internal'
    DB_NAME = 'patient_survey_db'
    DB_CREDS = credentials('db-creds')
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
            echo "DB_USER=${DB_USER}" >> .env
            echo "DB_PASSWORD=${DB_PASSWORD}" >> .env
            echo "DB_NAME=${DB_NAME}" >> .env
          '''
        }
      }
    }

    stage('Install Dependencies') {
      steps {
        sh '''
          python --version
          pip install --upgrade pip
          pip install -r requirements.txt
        '''
      }
    }

    stage('Run Tests') {
      steps {
        sh '''
          pytest tests --junitxml=test-results/results.xml
        '''
      }
    }

    stage('Build & Push Docker Image') {
      steps {
        script {
          docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
            docker.build("urszulach/epa-feedback-app:latest").push()
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


