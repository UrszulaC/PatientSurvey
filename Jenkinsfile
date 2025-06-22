pipeline {
    agent {
        docker {
            image 'python:3.10-slim'
            args '-u root --cache-from python:3.10-slim'
        }
    }

    environment {
        DOCKER_USER = credentials('docker-hub-creds')
        VENV_PATH = '/opt/venv'
    }

    stages {
        // Simple checkout doesn't need script block
        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        // Needs script block for error handling
        stage('Setup Environment') {
            steps {
                script {
                    try {
                        sh '''
                            python -m pip install --upgrade pip
                            python -m venv $VENV_PATH
                            . $VENV_PATH/bin/activate
                        '''
                    } catch (e) {
                        error("Failed to setup environment: ${e}")
                    }
                }
            }
        }

        // Needs script block for withEnv
        stage('Install Dependencies') {
            steps {
                script {
                    withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
                        sh '''
                            pip install -r requirements.txt
                            pip list
                        '''
                    }
                }
            }
        }

        // Needs script block for withEnv
        stage('Run Tests') {
            steps {
                script {
                    withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
                        sh 'pytest tests --junitxml=test-results/results.xml'
                    }
                }
            }
            post {
                always {
                    junit 'test-results/results.xml'
                }
            }
        }

        // Needs script block for Docker operations
        stage('Build and Push Docker Image') {
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
            cleanWs()
        }
    }
}
