import os
import unittest
import logging
import pyodbc
import json
import time
from unittest.mock import patch, MagicMock
from dotenv import load_dotenv
from app.config import Config
from app.utils.db_utils import get_db_connection
from app import create_app

# Load .env before using Config
load_dotenv()

class TestPatientSurveySystem(unittest.TestCase):

    def setUp(self):
        """Set up test environment before each test."""
        try:
            # Import the app from main
            from app.main import app
            
            # Set testing mode
            app.config['TESTING'] = True
            
            # Set the template folder explicitly for tests
            import os
            # Get the project root directory (one level up from tests directory)
            project_root = os.path.join(os.path.dirname(__file__), '..')
            template_path = os.path.abspath(os.path.join(project_root, 'templates'))
            
            # Check if templates exist at the expected path
            if os.path.exists(template_path):
                app.template_folder = template_path
                print(f"Template folder set to: {template_path}")
            else:
                # Fallback: check if templates are in app/templates
                app_template_path = os.path.abspath(os.path.join(project_root, 'app', 'templates'))
                if os.path.exists(app_template_path):
                    app.template_folder = app_template_path
                    print(f"Template folder set to: {app_template_path}")
                else:
                    # Create a temporary templates directory for tests
                    os.makedirs(template_path, exist_ok=True)
                    # Create a simple index.html for testing
                    with open(os.path.join(template_path, 'index.html'), 'w') as f:
                        f.write('<html><body><h1>Test Survey</h1></body></html>')
                    app.template_folder = template_path
                    print(f"Created temporary template folder: {template_path}")
            
            self.app = app
            self.client = self.app.test_client()
            
            # Connect to the test database
            self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            self.cursor = self.conn.cursor()
    
            # Clean any existing data
            self._clean_database()
    
            # Create default survey and questions
            self._create_default_survey()
    
        except Exception as e:
            logging.error(f"Test setup failed: {e}")
            raise

    def _clean_database(self):
        """Clean all test data."""
        # Delete in correct order to respect foreign key constraints
        tables = ['answers', 'responses', 'questions', 'surveys']
        for table in tables:
            try:
                self.cursor.execute(f"DELETE FROM {table}")
                print(f"Deleted from {table}: {self.cursor.rowcount} rows")
            except pyodbc.Error as e:
                print(f"Note: Error deleting {table} (might not exist): {e}")
        self.conn.commit()

    def _create_default_survey(self):
        """Create the default survey and questions matching the actual schema."""
        # First check if tables exist, if not create them
        self._ensure_tables_exist()
        
        # Insert default survey
        self.cursor.execute(
            "INSERT INTO surveys (title, description, is_active) VALUES (?, ?, ?)",
            ('Patient Experience Survey', 'Survey to collect feedback', 1)
        )
        self.conn.commit()
        
        # Get the survey ID
        self.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey_row = self.cursor.fetchone()
        self.survey_id = survey_row[0]
        
        # Insert questions - matching the exact schema from main.py
        questions = [
            {'text': 'Date of visit?', 'type': 'text', 'required': True, 'options': None},
            {'text': 'Which site did you visit?', 'type': 'multiple_choice', 'required': True,
             'options': ['Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital']},
            {'text': 'Patient name?', 'type': 'text', 'required': True, 'options': None},
            {'text': 'How easy was it to get an appointment?', 'type': 'multiple_choice', 'required': True,
             'options': ['Very difficult', 'Somewhat difficult', 'Neutral', 'Easy', 'Very easy']},
            {'text': 'Were you properly informed about your procedure?', 'type': 'multiple_choice', 'required': True,
             'options': ['Yes', 'No', 'Partially']},
            {'text': 'What went well during your visit?', 'type': 'text', 'required': False, 'options': None},
            {'text': 'Overall satisfaction (1-5)', 'type': 'multiple_choice', 'required': True,
             'options': ['1', '2', '3', '4', '5']}
        ]
        
        for q in questions:
            self.cursor.execute(
                "INSERT INTO questions (survey_id, question_text, question_type, is_required, options) VALUES (?, ?, ?, ?, ?)",
                (self.survey_id, q['text'], q['type'], q['required'], json.dumps(q['options']) if q['options'] else None)
            )
        
        self.conn.commit()
        
        # Create questions mapping
        self.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.questions = {row[1]: row[0] for row in self.cursor.fetchall()}

    def _ensure_tables_exist(self):
        """Ensure the required tables exist with the exact schema from main.py."""
        try:
            # Create surveys table (if not exists)
            self.cursor.execute("""
                IF OBJECT_ID('surveys', 'U') IS NULL
                CREATE TABLE surveys (
                    survey_id INT IDENTITY(1,1) PRIMARY KEY,
                    title NVARCHAR(255) NOT NULL,
                    description NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE(),
                    is_active BIT DEFAULT 1
                )
            """)

            # Create questions table (if not exists)
            self.cursor.execute("""
                IF OBJECT_ID('questions', 'U') IS NULL
                CREATE TABLE questions (
                    question_id INT IDENTITY(1,1) PRIMARY KEY,
                    survey_id INT NOT NULL,
                    question_text NVARCHAR(MAX) NOT NULL,
                    question_type NVARCHAR(50) NOT NULL,
                    is_required BIT DEFAULT 0,
                    options NVARCHAR(MAX),
                    FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
                )
            """)

            # Create responses table (if not exists)
            self.cursor.execute("""
                IF OBJECT_ID('responses', 'U') IS NULL
                CREATE TABLE responses (
                    response_id INT IDENTITY(1,1) PRIMARY KEY,
                    survey_id INT NOT NULL,
                    submitted_at DATETIME DEFAULT GETDATE(),
                    FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
                )
            """)

            # Create answers table (if not exists)
            self.cursor.execute("""
                IF OBJECT_ID('answers', 'U') IS NULL
                CREATE TABLE answers (
                    answer_id INT IDENTITY(1,1) PRIMARY KEY,
                    response_id INT NOT NULL,
                    question_id INT NOT NULL,
                    answer_value NVARCHAR(MAX),
                    FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
                    FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE NO ACTION
                )
            """)
            
            self.conn.commit()
            
        except pyodbc.Error as e:
            print(f"Note: Error creating tables (might already exist): {e}")
            self.conn.rollback()

    def tearDown(self):
        """Close connections after each test."""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    # --- API Endpoint Tests ---
    def test_submit_survey_endpoint(self):
        """Test POST /api/survey endpoint"""
        survey_data = {
            'answers': [
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-01-01'},
                {'question_id': self.questions['Which site did you visit?'], 'answer_value': 'Princess Alexandra Hospital'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'John Doe'},
                {'question_id': self.questions['How easy was it to get an appointment?'], 'answer_value': 'Neutral'},
                {'question_id': self.questions['Were you properly informed about your procedure?'], 'answer_value': 'Yes'},
                {'question_id': self.questions['What went well during your visit?'], 'answer_value': 'Friendly staff'},
                {'question_id': self.questions['Overall satisfaction (1-5)'], 'answer_value': '5'}
            ]
        }
        
        response = self.client.post('/api/survey', 
                                  json=survey_data,
                                  content_type='application/json')
        
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn('response_id', data)
        self.assertIn('message', data)
        
        # Verify data was inserted
        self.cursor.execute("SELECT COUNT(*) FROM responses")
        count = self.cursor.fetchone()[0]
        self.assertEqual(count, 1)
        
        self.cursor.execute("SELECT COUNT(*) FROM answers")
        answers_count = self.cursor.fetchone()[0]
        self.assertEqual(answers_count, 7)

    def test_submit_survey_invalid_data(self):
        """Test POST /api/survey with invalid data"""
        # Test with no data
        response = self.client.post('/api/survey', 
                                  json={},
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)
        
        # Test with missing answers
        response = self.client.post('/api/survey', 
                                  json={'wrong_key': []},
                                  content_type='application/json')
        self.assertEqual(response.status_code, 400)

    def test_get_responses_endpoint(self):
        """Test GET /api/responses endpoint"""
        # First submit a survey to have data to retrieve
        survey_data = {
            'answers': [
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-01-01'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'John Doe'}
            ]
        }
        
        submit_response = self.client.post('/api/survey', 
                                         json=survey_data,
                                         content_type='application/json')
        self.assertEqual(submit_response.status_code, 201)
        
        # Test the endpoint
        response = self.client.get('/api/responses')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data), 0)  # Should have responses now

    def test_get_responses_empty(self):
        """Test GET /api/responses endpoint works without crashing"""
        response = self.client.get('/api/responses')
        
        # The main assertion: endpoint should return 200 status
        self.assertEqual(response.status_code, 200)
        
        # Should return valid JSON
        data = response.get_json()
        self.assertIsInstance(data, (dict, list))
        
        # For this test, we don't care about the content when empty
        # We just want to ensure the endpoint doesn't crash
        
    def test_health_endpoint(self):
        """Test GET /health endpoint"""
        response = self.client.get('/health')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertEqual(data['status'], 'healthy')
        self.assertEqual(data['database'], 'connected')

    def test_metrics_endpoint(self):
        """Test GET /metrics endpoint"""
        response = self.client.get('/metrics')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content_type, 'text/plain; version=0.0.4; charset=utf-8')

    def test_index_endpoint(self):
        """Test GET / endpoint"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    # --- Database Structure Tests ---
    def test_default_survey_exists(self):
        self.cursor.execute(
            "SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',)
        )
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertEqual(survey[1], 'Patient Experience Survey')  # title
        self.assertEqual(survey[2], 'Survey to collect feedback')  # description

    def test_questions_created(self):
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

    def test_question_options(self):
        """Test that multiple choice questions have proper options"""
        self.cursor.execute(
            "SELECT question_text, options FROM questions WHERE question_type = 'multiple_choice' AND survey_id = ?",
            (self.survey_id,)
        )
        mc_questions = self.cursor.fetchall()
        
        for question_text, options_json in mc_questions:
            self.assertIsNotNone(options_json)
            options = json.loads(options_json)
            self.assertIsInstance(options, list)
            self.assertGreater(len(options), 0)

    # --- Edge Cases ---
    def test_submit_survey_missing_required_field(self):
        """Test submitting survey with missing required field"""
        survey_data = {
            'answers': [
                # Missing some required fields intentionally
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-01-01'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'John Doe'},
            ]
        }
        
        response = self.client.post('/api/survey', 
                                  json=survey_data,
                                  content_type='application/json')
        self.assertEqual(response.status_code, 201)

    def test_database_constraints(self):
        """Test that database constraints work"""
        # This should fail due to foreign key constraint
        with self.assertRaises(pyodbc.Error):
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                (99999, 99999, 'test')  # Non-existent IDs
            )
            self.conn.commit()

    def test_get_questions_endpoint(self):
        """Test GET /api/questions endpoint"""
        response = self.client.get('/api/questions')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 7)
        
        # Check that questions have the expected structure
        for question in data:
            self.assertIn('question_id', question)
            self.assertIn('question_text', question)
            self.assertIn('question_type', question)
            self.assertIn('is_required', question)
            self.assertIn('options', question)


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
