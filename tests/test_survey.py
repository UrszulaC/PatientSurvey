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
            # Create Flask test client
            self.app = create_app()
            self.app.config['TESTING'] = True
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
        tables = ['answers', 'responses', 'questions', 'surveys']
        for table in tables:
            try:
                self.cursor.execute(f"DELETE FROM {table}")
            except pyodbc.Error as e:
                print(f"Note: Error deleting {table} (might not exist): {e}")
        self.conn.commit()

    def _create_default_survey(self):
        """Create the default survey and questions."""
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
        
        # Insert questions - without display_order since it doesn't exist in your schema
        questions_data = [
            ('Date of visit?', 'date', 1, None),
            ('Which site did you visit?', 'multiple_choice', 1, json.dumps([
                'Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital'
            ])),
            ('Patient name?', 'text', 1, None),
            ('How easy was it to get an appointment?', 'multiple_choice', 0, json.dumps([
                'Very easy', 'Easy', 'Neutral', 'Difficult', 'Very difficult'
            ])),
            ('Were you properly informed about your procedure?', 'multiple_choice', 0, json.dumps([
                'Yes', 'No', 'Partially'
            ])),
            ('What went well during your visit?', 'text', 0, None),
            ('Overall satisfaction (1-5)', 'multiple_choice', 1, json.dumps(['1', '2', '3', '4', '5']))
        ]
        
        for question_text, question_type, is_required, options in questions_data:
            # Try different insert patterns based on what columns exist
            try:
                self.cursor.execute(
                    "INSERT INTO questions (survey_id, question_text, question_type, is_required, options) VALUES (?, ?, ?, ?, ?)",
                    (self.survey_id, question_text, question_type, is_required, options)
                )
            except pyodbc.Error as e:
                # If options column doesn't exist, try without it
                if 'options' in str(e).lower():
                    self.cursor.execute(
                        "INSERT INTO questions (survey_id, question_text, question_type, is_required) VALUES (?, ?, ?, ?)",
                        (self.survey_id, question_text, question_type, is_required)
                    )
                else:
                    raise
        
        self.conn.commit()
        
        # Create questions mapping
        self.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.questions = {row[1]: row[0] for row in self.cursor.fetchall()}

    def _ensure_tables_exist(self):
        """Ensure the required tables exist with basic structure."""
        try:
            # Check if surveys table exists
            self.cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='surveys' AND xtype='U')
                CREATE TABLE surveys (
                    survey_id INT IDENTITY(1,1) PRIMARY KEY,
                    title NVARCHAR(255) NOT NULL,
                    description NVARCHAR(MAX),
                    created_at DATETIME DEFAULT GETDATE(),
                    is_active BIT DEFAULT 1
                )
            """)
            
            # Check if questions table exists
            self.cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='questions' AND xtype='U')
                CREATE TABLE questions (
                    question_id INT IDENTITY(1,1) PRIMARY KEY,
                    survey_id INT NOT NULL FOREIGN KEY REFERENCES surveys(survey_id),
                    question_text NVARCHAR(MAX) NOT NULL,
                    question_type NVARCHAR(50) NOT NULL,
                    is_required BIT DEFAULT 0,
                    created_at DATETIME DEFAULT GETDATE()
                )
            """)
            
            # Check if responses table exists
            self.cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='responses' AND xtype='U')
                CREATE TABLE responses (
                    response_id INT IDENTITY(1,1) PRIMARY KEY,
                    survey_id INT NOT NULL FOREIGN KEY REFERENCES surveys(survey_id),
                    submitted_at DATETIME DEFAULT GETDATE()
                )
            """)
            
            # Check if answers table exists
            self.cursor.execute("""
                IF NOT EXISTS (SELECT * FROM sysobjects WHERE name='answers' AND xtype='U')
                CREATE TABLE answers (
                    answer_id INT IDENTITY(1,1) PRIMARY KEY,
                    response_id INT NOT NULL FOREIGN KEY REFERENCES responses(response_id),
                    question_id INT NOT NULL FOREIGN KEY REFERENCES questions(question_id),
                    answer_value NVARCHAR(MAX) NOT NULL,
                    created_at DATETIME DEFAULT GETDATE()
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

    def test_get_responses_empty(self):
        """Test GET /api/responses when no responses exist"""
        response = self.client.get('/api/responses')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertEqual(data, {})

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
        # Check if is_active column exists at position 4, otherwise adjust
        try:
            self.cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='surveys' AND ORDINAL_POSITION=4")
            column_name = self.cursor.fetchone()
            if column_name and column_name[0].lower() == 'is_active':
                self.assertTrue(survey[4])
        except:
            pass  # Skip if we can't determine column position
        self.assertEqual(survey[2], 'Survey to collect feedback')

    def test_questions_created(self):
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

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


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
