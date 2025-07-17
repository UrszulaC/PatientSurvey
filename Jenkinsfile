pipeline {
  agent any

  environment {
    DB_HOST = '172.17.0.1'
    DB_NAME = 'patient_survey_db'  
  }

  options {
    timeout(time: 20, unit: 'MINUTES')
  }
  stages {
    stage('Create .env File') {
      steps {
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            echo "DB_HOST=${DB_HOST}" > .env
            echo "DB_USER=$DB_USER" >> .env
            echo "DB_PASSWORD=$DB_PASSWORD" >> .env
            echo "DB_NAME=${DB_NAME}" >> .env
          '''
        }
      }
    }
  

    stage('Install Dependencies') {
      steps {
        sh '''
          python3 --version
          pip3 install --upgrade pip
          pip install -r requirements.txt
        '''
      }
    }
    stage('Security Scan') {
      steps {
-       sh '''
+       sh '''
          pip install --user bandit
+         export PATH=$HOME/.local/bin:$PATH
          bandit -r app/ -lll
        '''
      }
    }


    stage('Run Tests') {
      steps {
        withCredentials([
          usernamePassword(credentialsId: 'db-creds', usernameVariable: 'DB_USER', passwordVariable: 'DB_PASSWORD')
        ]) {
          sh '''
            export PATH=$HOME/.local/bin:$PATH
            export DB_USER=$DB_USER
            export DB_PASSWORD=$DB_PASSWORD
            python3 -m xmlrunner discover -s tests -o test-results
          '''
        }
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
      script {
        if (fileExists('test-results/results.xml')) {
          junit 'test-results/results.xml'
        } else {
          echo '⚠️ No test results found to publish.'
        }
      }
      cleanWs()
    }
  }
}


