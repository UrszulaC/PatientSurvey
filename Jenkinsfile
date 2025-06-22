pipeline {
  agent {
    node {
      label 'docker'
    }
  }

  options {
    timeout(time: 1, unit: 'HOURS')  // Global timeout
  }

  environment {
    DOCKER_USER = credentials('docker-hub-creds')
    VENV_PATH = "${env.WORKSPACE}/venv"
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Setup') {
      steps {
        script {
          docker.image('python:3.10-slim').inside('-u root --rm') {
            sh """
              python -m venv $VENV_PATH
              . $VENV_PATH/bin/activate
              pip install --upgrade pip
            """
          }
        }
      }
    }

    stage('Install') {
      steps {
        script {
          docker.image('python:3.10-slim').inside('-u root --rm') {
            withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
              timeout(time: 10, unit: 'MINUTES') {
                sh """
                  . $VENV_PATH/bin/activate
                  pip install -r requirements.txt
                """
              }
            }
          }
        }
      }
    }

    stage('Tests') {
      steps {
        script {
          docker.image('python:3.10-slim').inside('-u root --rm') {
            withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
              timeout(time: 15, unit: 'MINUTES') {
                sh """
                  . $VENV_PATH/bin/activate
                  pytest tests --junitxml=test-results/results.xml
                """
              }
            }
          }
        }
      }
    }

    stage('Build') {
      steps {
        script {
          timeout(time: 30, unit: 'MINUTES') {
            docker.withRegistry('https://index.docker.io/v1/', 'docker-hub-creds') {
              try {
                docker.build("urszulach/epa-feedback-app:latest").push()
              } finally {
                sh 'docker system prune -f || true'
              }
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
