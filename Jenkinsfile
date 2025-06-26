pipeline {
  agent {
    docker {
      image 'python:3.10-slim'
      args '-u root'
    }
  }

  environment {
    VENV_DIR = 'venv'
  }

  options {
    timeout(time: 15, unit: 'MINUTES')
  }

  stages {
    stage('Prepare Environment') {
      steps {
        sh '''
          apt-get update && apt-get install -y \
            python3-venv \
            gcc \
            default-libmysqlclient-dev

          python -m venv ${VENV_DIR}
          . ${VENV_DIR}/bin/activate && pip install --upgrade pip
          . ${VENV_DIR}/bin/activate && pip install -r requirements.txt
        '''
      }
    }

    stage('Run Tests') {
      steps {
        sh '''
          echo "✅ Running pytest..."
          . ${VENV_DIR}/bin/activate
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
      // Publish test results if they exist
      script {
        if (fileExists('test-results/results.xml')) {
          junit 'test-results/results.xml'
        } else {
          echo '⚠️ No test results found to publish.'
        }
      }

      // Clean workspace after each build
      cleanWs()
    }
  }
}
