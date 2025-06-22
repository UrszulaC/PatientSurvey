pipeline {
    agent {
        node {
            label 'docker'  // Specify a label that matches your agents with Docker
        }
    }

    environment {
        DOCKER_USER = credentials('docker-hub-creds')
        VENV_PATH = "${env.WORKSPACE}/venv"
    }

    stages {
        stage('Checkout Code') {
            steps {
                checkout scm
            }
        }

        stage('Setup Environment') {
            steps {
                script {
                    docker.image('python:3.10-slim').inside('-u root') {
                        sh '''
                            python -m pip install --upgrade pip
                            python -m venv $VENV_PATH
                            . $VENV_PATH/bin/activate
                        '''
                    }
                }
            }
        }

        stage('Install Dependencies') {
            steps {
                script {
                    docker.image('python:3.10-slim').inside('-u root') {
                        withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
                            sh '''
                                . $VENV_PATH/bin/activate
                                pip install -r requirements.txt
                                pip list
                            '''
                        }
                    }
                }
            }
        }

        stage('Run Tests') {
            steps {
                script {
                    docker.image('python:3.10-slim').inside('-u root') {
                        withEnv(["PATH+VENV=${VENV_PATH}/bin"]) {
                            sh '''
                                . $VENV_PATH/bin/activate
                                pytest tests --junitxml=test-results/results.xml
                            '''
                        }
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
