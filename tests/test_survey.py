import os
import logging
from dotenv import load_dotenv
import unittest
import pyodbc
from unittest.mock import patch
from app.config import Config
from app.utils.db_utils import get_db_connection
import json
import time

# Load .env before using Config
load_dotenv()
logging.basicConfig(level=logging.INFO)

class TestPatientSurveySystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Ensure test DB exists and connect once for class"""
        try:
            cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        except pyodbc.ProgrammingError:
            # Database does not exist → create it
            logging.info(f"Test database {Config.DB_TEST_NAME} not found. Creating...")
            conn_master = get_db_connection(database_name=None)
            conn_master.autocommit = True
            cursor = conn_master.cursor()
            cursor.execute(f"IF DB_ID('{Config.DB_TEST_NAME}') IS NULL CREATE DATABASE [{Config.DB_TEST_NAME}]")
            cursor.close()
            conn_master.close()
            cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        cls.cursor = cls.conn.cursor()

        # Initialize tables if missing
        from app.main import create_survey_tables
        create_survey_tables(cls.conn)

        # Cache survey_id and question IDs
        cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        cls.survey_id = cls.cursor.fetchone()[0]

        cls.cursor.execute("SELECT question_text, question_id FROM questions WHERE survey_id = ?", (cls.survey_id,))
        cls.questions = {row[0]: row[1] for row in cls.cursor.fetchall()}

    @classmethod
    def tearDownClass(cls):
        """Close class-level connections"""
        try:
            if hasattr(cls, 'cursor') and cls.cursor:
                cls.cursor.close()
            if hasattr(cls, 'conn') and cls.conn:
                cls.conn.close()
        except Exception as e:
            logging.warning(f"Error closing test DB connections: {e}")

    def setUp(self):
        """Clean child tables before each test"""
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        self.conn.commit()

    def tearDown(self):
        """Nothing needed, DB persists for next test"""
        pass

    # --- Basic DB Structure Tests ---

    def test_default_survey_exists(self):
        self.cursor.execute("SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey[4])
        self.assertEqual(survey[2], 'Survey to collect feedback')

    def test_questions_created(self):
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

        self.cursor.execute("SELECT question_type, is_required, options FROM questions WHERE question_text = ?", 
                            ('Which site did you visit?',))
        q = self.cursor.fetchone()
        self.assertEqual(q[0], 'multiple_choice')
        self.assertTrue(q[1])
        self.assertEqual(json.loads(q[2]), ['Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital'])

    # --- Survey Conducting Tests ---

    @patch('builtins.input')
    def test_complete_survey_flow(self, mock_input):
        """Test full survey submission with all answers"""
        mock_input.side_effect = [
            '2023-01-01',  # Date of visit
            '1',           # Site
            'John Doe',    # Patient name
            '3',           # Ease
            '1',           # Informed
            'Friendly staff', # Optional feedback
            '5'            # Rating
        ]

        from app.main import conduct_survey
        conduct_survey(self.conn)

        # Verify responses inserted
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        # Verify all 7 answers recorded
        self.cursor.execute("SELECT COUNT(*) FROM answers WHERE response_id = ?", (response[0],))
        self.assertEqual(self.cursor.fetchone()[0], 7)

        # Verify optional field recorded correctly
        self.cursor.execute("SELECT answer_value FROM answers WHERE question_id = ? AND response_id = ?", 
                            (self.questions['What went well during your visit?'], response[0]))
        self.assertEqual(self.cursor.fetchone()[0], 'Friendly staff')

    @patch('builtins.input')
    def test_optional_field_skipped(self, mock_input):
        """Optional field should default to '[No response]' if skipped"""
        mock_input.side_effect = [
            '2023-01-01', '1', 'John', '3', '1',
            '',  # Skip optional
            '5'
        ]

        from app.main import conduct_survey
        conduct_survey(self.conn)

        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        self.cursor.execute("SELECT answer_value FROM answers WHERE question_id = ? AND response_id = ?", 
                            (self.questions['What went well during your visit?'], response[0]))
        self.assertEqual(self.cursor.fetchone()[0], '[No response]')

    @patch('builtins.input')
    def test_invalid_multiple_choice_input(self, mock_input):
        """Invalid numeric choice for multiple-choice question should retry"""
        mock_input.side_effect = [
            '2023-01-01', '5', '1', 'John', '3', '1', 'Good', '5'
        ]

        from app.main import conduct_survey
        with patch('builtins.print') as mock_print:
            conduct_survey(self.conn)
            output = "\n".join(str(c) for c in mock_print.call_args_list)
            self.assertIn("Please enter a number between 1 and 3", output)

        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    # --- View Responses Tests ---

    def test_view_empty_responses(self):
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            mock_print.assert_called_with("\nNo responses found in the database.")

    def test_view_multiple_responses(self):
    """Test view_responses with multiple survey entries"""
    # Create first test response
    self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
    self.cursor.execute("SELECT SCOPE_IDENTITY()")
    row = self.cursor.fetchone()
    if row is None or row[0] is None:
        # Fallback to @@IDENTITY
        self.cursor.execute("SELECT @@IDENTITY")
        row = self.cursor.fetchone()
        if row is None or row[0] is None:
            raise Exception("Failed to retrieve response_id for first insert")
    response1 = int(row[0])

    # Create second test response
    self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
    self.cursor.execute("SELECT SCOPE_IDENTITY()")
    row = self.cursor.fetchone()
    if row is None or row[0] is None:
        # Fallback to @@IDENTITY
        self.cursor.execute("SELECT @@IDENTITY")
        row = self.cursor.fetchone()
        if row is None or row[0] is None:
            raise Exception("Failed to retrieve response_id for second insert")
    response2 = int(row[0])

    # Add sample answers
    sample_answers = [
        (response1, self.questions['Date of visit?'], '2023-01-01'),
        (response1, self.questions['Which site did you visit?'], 'Princess Alexandra Hospital'),
        (response2, self.questions['Date of visit?'], '2023-01-02'),
        (response2, self.questions['Which site did you visit?'], 'Herts & Essex Hospital')
    ]

    for answer in sample_answers:
        self.cursor.execute("""
            INSERT INTO answers (response_id, question_id, answer_value)
            VALUES (?, ?, ?)
        """, answer)

    self.conn.commit()

    # Test the view_responses function
    from app.main import view_responses
    with patch('builtins.print') as mock_print:
        view_responses(self.conn)

        # Verify responses were displayed
        output = "\n".join(str(call) for call in mock_print.call_args_list)
        self.assertIn(f"Response ID: {response1}", output)
        self.assertIn(f"Response ID: {response2}", output)
        self.assertIn("Princess Alexandra Hospital", output)
        self.assertIn("Herts & Essex Hospital", output)


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
