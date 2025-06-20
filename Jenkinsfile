pipeline {
  agent any

  environment {
    DOCKER_USER = credentials('docker-hub-creds')
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Setup Python') {
      steps {
        sh '''
          python3 -m pip install --upgrade pip
          python3 -m venv venv
          . venv/bin/activate
        '''
      }
    }

    stage('Install Dependencies') {
      steps {
        sh '''
          . venv/bin/activate
          pip install -r requirements.txt
        '''
      }
    }

    stage('Run Tests') {
      steps {
        sh '''
          . venv/bin/activate
          pytest tests
        '''
      }
    }

    stage('Docker Build and Push') {
      steps {
        sh '''
          docker login -u $DOCKER_USER_USR -p $DOCKER_USER_PSW
          docker build -t urszulach/epa-feedback-app:latest .
          docker push urszulach/epa-feedback-app:latest
        '''
      }
    }
  }
}
