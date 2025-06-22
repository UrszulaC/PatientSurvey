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

    // NEW STAGE ADDED HERE
    stage('Setup Python Environment') {
      steps {
        sh '''
          sudo apt-get update
          sudo apt-get install -y python3-venv python3-pip
        '''
      }
    }

    stage('Install Dependencies') {
      steps {
        sh '''
          python3 -m venv venv
          . venv/bin/activate
          pip install -r requirements.txt
        '''
      }
    }

    // Rest of your existing stages...
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
