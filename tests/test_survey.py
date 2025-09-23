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
            # CLEAR PROMETHEUS REGISTRY FIRST - THIS FIXES THE DUPLICATION ERROR
            self._clear_prometheus_registry()
            
            # Create app instance with TESTING configuration
            app = create_app()
            app.config['TESTING'] = True
            app.config['DB_NAME'] = Config.DB_TEST_NAME  # Force test database
            
            # Patch the get_db_connection to use test database
            self.get_db_connection_patcher = patch('app.main.get_db_connection')
            self.mock_get_db_connection = self.get_db_connection_patcher.start()
            self.mock_get_db_connection.side_effect = lambda database_name=None: get_db_connection(database_name or Config.DB_TEST_NAME)
            
            self.app = app
            self.client = self.app.test_client()

            # Connect to the test database for test setup
            self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            self.cursor = self.conn.cursor()

            # Clean any existing data
            self._clean_database()

            # Create default survey and questions
            self._create_default_survey()

        except Exception as e:
            logging.error(f"Test setup failed: {e}")
            raise

    def tearDown(self):
        """Close connections after each test."""
        if hasattr(self, 'get_db_connection_patcher'):
            self.get_db_connection_patcher.stop()
            
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    # ... rest of your test methods remain the same ...
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
        # Ensure we have valid question IDs for ALL required questions
        self.assertIsNotNone(self.questions, "Questions mapping should not be None")
        self.assertGreater(len(self.questions), 0, "Should have questions available")
        
        print(f"DEBUG: Available questions: {self.questions}")
        
        # Create a complete survey submission with all required questions
        survey_data = {
            'answers': [
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-01-01'},
                {'question_id': self.questions['Which site did you visit?'], 'answer_value': 'Princess Alexandra Hospital'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'John Doe'},
                {'question_id': self.questions['How easy was it to get an appointment?'], 'answer_value': 'Neutral'},
                {'question_id': self.questions['Were you properly informed about your procedure?'], 'answer_value': 'Yes'},
                {'question_id': self.questions['Overall satisfaction (1-5)'], 'answer_value': '5'}
                # Optional question omitted intentionally to test partial submission
            ]
        }
        
        print(f"DEBUG: Submitting survey data: {survey_data}")
        
        submit_response = self.client.post('/api/survey', 
                                         json=survey_data,
                                         content_type='application/json')
        print(f"DEBUG: Submit response status: {submit_response.status_code}")
        print(f"DEBUG: Submit response data: {submit_response.get_json()}")
        
        self.assertEqual(submit_response.status_code, 201, 
                        f"Survey submission failed: {submit_response.get_json()}")
        
        # Test the endpoint
        response = self.client.get('/api/responses')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertIsInstance(data, dict)
        self.assertGreater(len(data), 0)

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
