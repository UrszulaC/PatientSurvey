pipeline {
  agent {
    docker {
      image 'python:3.10'
      args '-u root'
    }
  }

  options {
    timeout(time: 15, unit: 'MINUTES')
  }

  stages {
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
