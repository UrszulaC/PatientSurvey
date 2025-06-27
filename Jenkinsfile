pipeline {
  agent {
    docker {
      image 'python:3.10'
      args '-u root'
    }
  }

  environment {
    DB_HOST = 'localhost'
    DB_NAME = 'patient_survey_db'
    DB_CREDS = credentials('db-creds')
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }

 stage('Setup Environment') {
  steps {
    script {
      writeFile file: '.env', text: """DB_HOST=${env.DB_HOST}
DB_USER=${env.DB_CREDS_USR}
DB_PASSWORD=${env.DB_CREDS_PSW}
DB_NAME=${env.DB_NAME}
"""
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
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            export DB_USER=$DB_USER
            export DB_PASSWORD=$DB_PASSWORD
            pytest tests --junitxml=test-results/results.xml
          '''
        }
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
