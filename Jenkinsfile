pipeline {
  agent any  // Docker build must run on the host

  environment {
    DOCKER_USER = credentials('docker-hub-creds')
  }

  options {
    timeout(time: 1, unit: 'HOURS')
  }

  stages {
    stage('Test in Docker') {
      agent {
        docker {
          image 'python:3.10-slim'
          args '-u root'
        }
      }
      steps {
        sh '''
          python -m venv venv
          . venv/bin/activate && \
          pip install --upgrade pip && \
          pip install -r requirements.txt && \
          pytest tests --junitxml=test-results/results.xml
        '''
      }
    }

    stage('Build & Push Docker Image') {
      agent any  // run on Jenkins host
      steps {
        script {
          docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
            def img = docker.build("urszulach/epa-feedback-app:latest")
            img.push()
          }
        }
      }
    }
  }

  post {
    always {
      node {
        sh 'docker ps -aq | xargs --no-run-if-empty docker stop || true'
        sh 'docker system prune -f || true'
        cleanWs()
      }
    }
  }
}
