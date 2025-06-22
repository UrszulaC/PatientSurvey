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
        stage('Checkout Code') {
            steps {
                checkout([
                    $class: 'GitSCM',
                    branches: scm.branches,
                    extensions: scm.extensions,
                    userRemoteConfigs: scm.userRemoteConfigs
                ])
            }
        }

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
