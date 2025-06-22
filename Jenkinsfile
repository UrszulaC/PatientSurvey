pipeline {
    agent {
        docker {
            image 'python:3.10-slim'
            args '-u root --cache-from python:3.10-slim'
        }
    }

    environment {
        DOCKER_USER = credentials('docker-hub-creds')
        VENV_PATH = '/opt/venv'  // System-wide venv location
    }

    stages {
        stage('Checkout Code') {
            steps {
                checkout scm
                sh 'git --version'  // Verify git is working
            }
        }

        stage('Setup Python Environment') {
            steps {
                sh '''
                    python -m pip install --upgrade pip
                    python -m venv $VENV_PATH
                    . $VENV_PATH/bin/activate
                    pip --version
                '''
            }
        }

        stage('Install Dependencies') {
            steps {
                sh '''
                    . $VENV_PATH/bin/activate
                    pip install -r requirements.txt
                    pip freeze  # Log installed packages
                '''
            }
        }

        stage('Run Tests') {
            steps {
                sh '''
                    . $VENV_PATH/bin/activate
                    pytest tests --cov=./ --cov-report=xml
                '''
            }
            post {
                always {
                    junit '**/test-reports/*.xml'  // If you generate JUnit reports
                    cobertura coberturaReportFile: '**/coverage.xml'
                }
            }
        }

        stage('Build Docker Image') {
            steps {
                script {
                    docker.build("urszulach/epa-feedback-app:latest")
                }
            }
        }

        stage('Push to Docker Hub') {
            steps {
                script {
                    docker.withRegistry('https://registry.hub.docker.com', 'docker-hub-creds') {
                        docker.image("urszulach/epa-feedback-app:latest").push()
                    }
                }
            }
        }
    }

    post {
        always {
            sh 'docker system prune -f || true'  // Cleanup docker artifacts
            cleanWs()  // Clean workspace
        }
        success {
            slackSend color: 'good', message: "Build ${env.BUILD_NUMBER} succeeded!"
        }
        failure {
            slackSend color: 'danger', message: "Build ${env.BUILD_NUMBER} failed!"
        }
    }
}
