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
        
        # Insert questions
        questions_data = [
            ('Date of visit?', 'date', 1, None, 1),
            ('Which site did you visit?', 'multiple_choice', 1, json.dumps([
                'Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital'
            ]), 2),
            ('Patient name?', 'text', 1, None, 3),
            ('How easy was it to get an appointment?', 'multiple_choice', 0, json.dumps([
                'Very easy', 'Easy', 'Neutral', 'Difficult', 'Very difficult'
            ]), 4),
            ('Were you properly informed about your procedure?', 'multiple_choice', 0, json.dumps([
                'Yes', 'No', 'Partially'
            ]), 5),
            ('What went well during your visit?', 'text', 0, None, 6),
            ('Overall satisfaction (1-5)', 'multiple_choice', 1, json.dumps(['1', '2', '3', '4', '5']), 7)
        ]
        
        for question_text, question_type, is_required, options, display_order in questions_data:
            self.cursor.execute(
                "INSERT INTO questions (survey_id, question_text, question_type, is_required, options, display_order) VALUES (?, ?, ?, ?, ?, ?)",
                (self.survey_id, question_text, question_type, is_required, options, display_order)
            )
        
        self.conn.commit()
        
        # Create questions mapping
        self.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.questions = {row[1]: row[0] for row in self.cursor.fetchall()}

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
        
        print(f"Response status: {response.status_code}")  # Debug
        print(f"Response data: {response.get_json()}")     # Debug
        
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertIn('response_id', data)
        self.assertIn('message', data)
        
        # Debug: Check what's actually in the database
        self.cursor.execute("SELECT * FROM responses")
        all_responses = self.cursor.fetchall()
        print(f"Responses in DB: {all_responses}")  # Debug
        
        self.cursor.execute("SELECT COUNT(*) FROM responses")
        count = self.cursor.fetchone()[0]
        print(f"Response count: {count}")  # Debug
        self.assertEqual(count, 1)
        
        self.cursor.execute("SELECT COUNT(*) FROM answers")
        answers_count = self.cursor.fetchone()[0]
        print(f"Answers count: {answers_count}")  # Debug
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
        self.assertIn('responses', data)

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
    def test_tables_created_correctly(self):
        self.cursor.execute(
            f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_TYPE='BASE TABLE' AND TABLE_CATALOG='{Config.DB_TEST_NAME}'"
        )
        tables = {row[0] for row in self.cursor.fetchall()}
        expected_tables = {'surveys', 'questions', 'responses', 'answers'}
        # Check that all expected tables exist (some might not be created yet)
        for table in expected_tables:
            self.assertIn(table, tables)

    def test_default_survey_exists(self):
        self.cursor.execute(
            "SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',)
        )
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey[4])  # is_active
        self.assertEqual(survey[2], 'Survey to collect feedback')

    def test_questions_created(self):
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

        self.cursor.execute(
            "SELECT question_type, is_required, options FROM questions WHERE question_text = ?",
            ('Which site did you visit?',)
        )
        question = self.cursor.fetchone()
        self.assertEqual(question[0], 'multiple_choice')
        self.assertTrue(question[1])
        self.assertEqual(json.loads(question[2]), [
            'Princess Alexandra Hospital',
            'St Margaret\'s Hospital',
            'Herts & Essex Hospital'
        ])

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
        
        # The API should still accept this (validation is now client-side)
        response = self.client.post('/api/survey', 
                                  json=survey_data,
                                  content_type='application/json')
        
        # Should still succeed since validation is now client-side
        self.assertEqual(response.status_code, 201)

    def test_database_constraints(self):
        with self.assertRaises(pyodbc.Error):
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                (1, 999, 'test')
            )
            self.conn.commit()

    def test_multiple_surveys(self):
        """Test that multiple survey submissions work correctly"""
        # Submit first survey
        survey_data_1 = {
            'answers': [
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-01-01'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'John Doe'}
            ]
        }
        
        response_1 = self.client.post('/api/survey', 
                                    json=survey_data_1,
                                    content_type='application/json')
        self.assertEqual(response_1.status_code, 201)
        
        # Submit second survey
        survey_data_2 = {
            'answers': [
                {'question_id': self.questions['Date of visit?'], 'answer_value': '2023-02-01'},
                {'question_id': self.questions['Patient name?'], 'answer_value': 'Jane Smith'}
            ]
        }
        
        response_2 = self.client.post('/api/survey', 
                                    json=survey_data_2,
                                    content_type='application/json')
        self.assertEqual(response_2.status_code, 201)
        
        # Verify both responses exist
        self.cursor.execute("SELECT COUNT(*) FROM responses")
        count = self.cursor.fetchone()[0]
        self.assertEqual(count, 2)
        
        self.cursor.execute("SELECT COUNT(*) FROM answers")
        answers_count = self.cursor.fetchone()[0]
        self.assertEqual(answers_count, 4)


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
