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

    stage('Install Dependencies') {
      steps {
        sh 'pip install -r requirements.txt'
      }
    }

    stage('Run Tests') {
      steps {
        sh 'pytest tests'
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
