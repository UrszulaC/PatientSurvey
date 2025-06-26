pipeline {
  agent {
    docker {
      image 'python:3.10-slim'
      args '-u root'
    }
  }

  environment {
    DOCKER_USER = credentials('docker-hub-creds')
  }

  options {
    timeout(time: 1, unit: 'HOURS')
  }

  stages {
    stage('Install Dependencies') {
      steps {
        sh '''
          python -m venv venv
          . venv/bin/activate
          pip install --upgrade pip
          pip install -r requirements.txt
        '''
      }
    }

    stage('Run Tests') {
      steps {
        sh '''
          . venv/bin/activate
          pytest tests --junitxml=test-results/results.xml
        '''
      }
    }

    stage('Build & Push Docker Image') {
      steps {
        script {
          timeout(time: 15, unit: 'MINUTES') {
            docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
              docker.build("urszulach/epa-feedback-app:latest").push()
            }
          }
        }
      }
    }
  }

  post {
    always {
      sh 'docker ps -aq | xargs --no-run-if-empty docker stop || true'
      sh 'docker system prune -f || true'
      cleanWs()
    }
  }
}
