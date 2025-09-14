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

    @classmethod
    def setUpClass(cls):
        """Set up Flask test client and database connection."""
        try:
            # Create Flask test client
            cls.app = create_app()
            cls.app.config['TESTING'] = True
            cls.client = cls.app.test_client()
            
            # Connect to the test database
            cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            cls.cursor = cls.conn.cursor()

            # Fetch the survey_id of the default survey
            cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
            survey_row = cls.cursor.fetchone()
            if not survey_row:
                raise Exception("Default survey not found in the database")
            cls.survey_id = survey_row[0]

            # Map question text to IDs for easy access in tests
            cls.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (cls.survey_id,))
            cls.questions = {row[1]: row[0] for row in cls.cursor.fetchall()}

        except Exception as e:
            logging.error(f"Database setup failed: {e}")
            raise

    def setUp(self):
        """Clean tables before each test."""
        try:
            self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            self.cursor = self.conn.cursor()

            # Delete from child tables first
            self.cursor.execute("DELETE FROM answers")
            self.cursor.execute("DELETE FROM responses")
            self.conn.commit()

        except Exception as e:
            logging.error(f"Test setup failed: {e}")
            raise

    def tearDown(self):
        """Close connections after each test."""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    @classmethod
    def tearDownClass(cls):
        """Close class-level connection."""
        if hasattr(cls, 'cursor') and cls.cursor:
            cls.cursor.close()
        if hasattr(cls, 'conn') and cls.conn:
            cls.conn.close()

    # --- API Endpoint Tests ---
    def test_get_questions_endpoint(self):
        """Test GET /api/questions endpoint"""
        response = self.client.get('/api/questions')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 7)
        
        # Check that questions have expected structure
        question = data[0]
        self.assertIn('question_id', question)
        self.assertIn('question_text', question)
        self.assertIn('question_type', question)
        self.assertIn('is_required', question)
        self.assertIn('options', question)

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
        
        # Verify data was actually inserted
        self.cursor.execute("SELECT COUNT(*) FROM responses")
        self.assertEqual(self.cursor.fetchone()[0], 1)
        
        self.cursor.execute("SELECT COUNT(*) FROM answers")
        self.assertEqual(self.cursor.fetchone()[0], 7)

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
        # First insert some test data
        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
        self.cursor.execute("SELECT SCOPE_IDENTITY()")
        response_id = int(self.cursor.fetchone()[0])
        
        # Insert answers
        for question_id in self.questions.values():
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                (response_id, question_id, 'test answer')
            )
        self.conn.commit()
        
        # Test the endpoint
        response = self.client.get('/api/responses')
        self.assertEqual(response.status_code, 200)
        
        data = response.get_json()
        self.assertIsInstance(data, dict)
        self.assertIn(str(response_id), data)
        self.assertEqual(len(data[str(response_id)]['answers']), 7)

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

    # --- Database Structure Tests (Keep these) ---
    def test_tables_created_correctly(self):
        self.cursor.execute(
            f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_TYPE='BASE TABLE' AND TABLE_CATALOG='{Config.DB_TEST_NAME}'"
        )
        tables = {row[0] for row in self.cursor.fetchall()}
        self.assertEqual(tables, {'surveys', 'questions', 'responses', 'answers'})

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


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
