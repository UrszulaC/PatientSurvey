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
    stage('Sanity Check') {
      steps {
        echo '✅ Inside Docker container'
        sh 'python --version'
        sh 'ls -la'
        sh 'cat requirements.txt'
      }
    }

    stage('Install Dependencies') {
      steps {
        sh '''
          apt-get update && apt-get install -y default-libmysqlclient-dev gcc
          python -m venv ${VENV_DIR}
          . ${VENV_DIR}/bin/activate && pip install --upgrade pip
          . ${VENV_DIR}/bin/activate && pip install -r requirements.txt
        '''
      }
    }

    stage('Test') {
      steps {
        sh '''
          echo "✅ Running tests"
          . ${VENV_DIR}/bin/activate
          pytest tests --junitxml=test-results/results.xml
        '''
      }
    }
  }

  post {
    always {
      node{
        junit 'test-results/results.xml'
        cleanWs()
      }
    }
  }
}


