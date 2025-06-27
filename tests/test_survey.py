import os
from dotenv import load_dotenv

# Load .env before using Config
load_dotenv()

import unittest
import mysql.connector
from unittest.mock import patch, MagicMock
from app.config import Config
import json

class TestPatientSurveySystem(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        """Set up test database and tables"""
        try:
            # Connect without specifying a database
            cls.connection = mysql.connector.connect(
                host=Config.DB_CONFIG['host'],
                user=Config.DB_CONFIG['user'],
                password=Config.DB_CONFIG['password']
            )
            cls.cursor = cls.connection.cursor()
            
            # Force reset the test database
            cls.cursor.execute("DROP DATABASE IF EXISTS patient_survey_test")
            cls.cursor.execute("CREATE DATABASE patient_survey_test")
            cls.cursor.execute("USE patient_survey_test")
            
            # Import and call the table creation function
            from app.main import create_survey_tables
            create_survey_tables(cls.connection)
            
            # Verify survey exists and has correct questions
            cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
            survey = cls.cursor.fetchone()
            if not survey:
                raise Exception("Default survey not created")
            
            cls.survey_id = survey[0]
            
            # Store question IDs for tests
            cls.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = %s ORDER BY question_id", (cls.survey_id,))
            cls.questions = {row[1]: row[0] for row in cls.cursor.fetchall()}
            
            if len(cls.questions) < 7:
                raise Exception(f"Expected 7 questions, found {len(cls.questions)}")
            
        except Exception as err:
            cls.tearDownClass()
            raise Exception(f"Test setup failed: {err}")

    @classmethod 
    def tearDownClass(cls):
        """Clean up test database"""
        try:
            if hasattr(cls, 'cursor'):
                cls.cursor.execute("DROP DATABASE IF EXISTS patient_survey_test")
                cls.connection.commit()
                cls.cursor.close()
            if hasattr(cls, 'connection') and cls.connection.is_connected():
                cls.connection.close()
        except Exception as e:
            print(f"Warning: Cleanup failed - {e}")

    def setUp(self):
        """Fresh connection for each test"""
        self.conn = mysql.connector.connect(
            host=Config.DB_CONFIG['host'],
            user=Config.DB_CONFIG['user'],
            password=Config.DB_CONFIG['password'],
            database="patient_survey_test"
        )
        self.cursor = self.conn.cursor(dictionary=True)
        
        # Ensure clean state but preserve survey structure
        self.cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        self.cursor.execute("TRUNCATE TABLE answers")
        self.cursor.execute("TRUNCATE TABLE responses")
        self.cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        self.conn.commit()

    def tearDown(self):
        """Cleanup after each test"""
        try:
            if hasattr(self, 'cursor'):
                self.cursor.close()
            if hasattr(self, 'conn') and self.conn.is_connected():
                self.conn.close()
        except Exception as e:
            print(f"Cleanup warning: {e}")

    # --- Database Structure Tests ---
    
    def test_tables_created_correctly(self):
        """Verify all tables exist with correct structure"""
        self.cursor.execute("SHOW TABLES")
        tables = {row['Tables_in_patient_survey_test'] for row in self.cursor.fetchall()}
        self.assertEqual(tables, {'surveys', 'questions', 'responses', 'answers'})
        
        # Verify surveys table columns
        self.cursor.execute("DESCRIBE surveys")
        survey_columns = {row['Field'] for row in self.cursor.fetchall()}
        self.assertEqual(survey_columns, {'survey_id', 'title', 'description', 'created_at', 'is_active'})

    def test_default_survey_exists(self):
        """Verify default survey was created"""
        self.cursor.execute("SELECT * FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey['is_active'])
        self.assertEqual(survey['description'], 'Survey to collect feedback')

    def test_questions_created(self):
        """Verify all questions exist"""
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = %s", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()['COUNT(*)'], 7)
        
        # Verify one sample question
        self.cursor.execute("""
            SELECT question_type, is_required, options 
            FROM questions 
            WHERE question_text = 'Which site did you visit?'
        """)
        question = self.cursor.fetchone()
        self.assertEqual(question['question_type'], 'multiple_choice')
        self.assertTrue(question['is_required'])
        self.assertEqual(json.loads(question['options']), 
                         ['Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital'])

    # --- Survey Conducting Tests ---
    
    @patch('builtins.input')
    def test_complete_survey_flow(self, mock_input):
        """Test full survey submission with all answers"""
        mock_input.side_effect = [
            '2023-01-01',  # Date of visit
            '1',           # Site (Princess Alexandra)
            'John Doe',    # Patient name
            '3',           # Ease (Neutral)
            '1',           # Informed (Yes)
            'Friendly staff',  # What went well
            '5'            # Rating (5)
        ]
        
        from app.main import conduct_survey
        conduct_survey(self.conn)
        
        # Verify response was created
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)
        
        # Verify all answers were saved
        self.cursor.execute("SELECT COUNT(*) FROM answers WHERE response_id = %s", (response['response_id'],))
        self.assertEqual(self.cursor.fetchone()['COUNT(*)'], 7)
        
        # Verify specific answers
        self.cursor.execute("""
            SELECT answer_value FROM answers 
            WHERE question_id = %s AND response_id = %s
        """, (self.questions['What went well during your visit?'], response['response_id']))
        self.assertEqual(self.cursor.fetchone()['answer_value'], 'Friendly staff')

    @patch('builtins.input')
    def test_required_field_validation(self, mock_input):
        """Test that required fields must be provided"""
        mock_input.side_effect = [
            '',            # Empty date (should reject)
            '2023-01-01', # Valid date
            '1', 'John', '3', '1', 'Good', '5'  # Rest of answers
        ]
        
        from app.main import conduct_survey
        conduct_survey(self.conn)
        
        # Verify response was created
        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    @patch('builtins.input')
    def test_optional_field_handling(self, mock_input):
        """Test optional fields can be skipped"""
        mock_input.side_effect = [
            '2023-01-01', '1', 'John', '3', '1', 
            '',  # Skip optional "what went well"
            '5'
        ]
        
        from app.main import conduct_survey
        conduct_survey(self.conn)
        
        # Verify response was created
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)
        
        # Verify optional answer was recorded as empty
        self.cursor.execute("""
            SELECT answer_value FROM answers 
            WHERE question_id = %s AND response_id = %s
        """, (self.questions['What went well during your visit?'], response['response_id']))
        self.assertEqual(self.cursor.fetchone()['answer_value'], '[No response]')

    # --- View Responses Tests ---
    
    def test_view_empty_responses(self):
        """Test viewing when no responses exist"""
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            mock_print.assert_called_with("\nNo responses found in the database.")

    def test_view_multiple_responses(self):
        """Test viewing multiple responses"""
        # Create test responses
        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (%s)", (self.survey_id,))
        response1 = self.cursor.lastrowid
        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (%s)", (self.survey_id,))
        response2 = self.cursor.lastrowid
        
        # Add answers
        sample_answers = [
            (response1, self.questions['Date of visit?'], '2023-01-01'),
            (response1, self.questions['Which site did you visit?'], 'Princess Alexandra Hospital'),
            (response2, self.questions['Date of visit?'], '2023-01-02'),
            (response2, self.questions['Which site did you visit?'], 'Herts & Essex Hospital')
        ]
        
        for answer in sample_answers:
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, %s, %s)
            """, answer)
        
        self.conn.commit()
        
        # Test view function
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            
            # Verify responses were displayed
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Response ID: {}".format(response1), output)
            self.assertIn("Response ID: {}".format(response2), output)
            self.assertIn("Princess Alexandra Hospital", output)
            self.assertIn("Herts & Essex Hospital", output)

    # --- Edge Cases ---
    
    @patch('builtins.input')
    def test_invalid_multiple_choice_input(self, mock_input):
        """Test handling of invalid multiple choice selections"""
        mock_input.side_effect = [
            '2023-01-01',
            '5',  # Invalid choice (only 3 options)
            '1',  # Then valid choice
            'John', '3', '1', 'Good', '5'
        ]
        
        from app.main import conduct_survey
        with patch('builtins.print') as mock_print:
            conduct_survey(self.conn)
            
            # Verify error message was shown
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Please enter a number between 1 and 3", output)
            
        # Verify response was still recorded
        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    def test_database_constraints(self):
        """Verify foreign key constraints work"""
        # Try to insert answer with invalid question ID
        with self.assertRaises(mysql.connector.Error):
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (1, 999, 'test')
            """)
            self.conn.commit()

    # --- Performance Tests ---
    
    def test_multiple_response_performance(self):
        """Test performance with many responses"""
        from app.main import view_responses
        
        # Create 100 test responses
        for i in range(100):
            self.cursor.execute("INSERT INTO responses (survey_id) VALUES (%s)", (self.survey_id,))
            response_id = self.cursor.lastrowid
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, %s, %s)
            """, (response_id, self.questions['Date of visit?'], f'2023-01-{i+1:02d}'))
        
        self.conn.commit()
        
        # Time the view operation
        import time
        start = time.time()
        view_responses(self.conn)
        duration = time.time() - start
        
        self.assertLess(duration, 1.0, "Viewing responses took too long")

if __name__ == "__main__":
    unittest.main()
