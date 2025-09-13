import os
import unittest
import pyodbc
import logging
from dotenv import load_dotenv
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
            # Attempt to connect to test DB
            cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        except pyodbc.ProgrammingError:
            # Database likely does not exist, create via master
            logging.info(f"Test database {Config.DB_TEST_NAME} not found. Creating...")
            conn_master = get_db_connection(database_name=None)
            conn_master.autocommit = True
            cursor = conn_master.cursor()
            cursor.execute(f"IF DB_ID('{Config.DB_TEST_NAME}') IS NULL CREATE DATABASE [{Config.DB_TEST_NAME}]")
            cursor.close()
            conn_master.close()
            # Connect again to newly created test DB
            cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        cls.cursor = cls.conn.cursor()

        # Initialize tables if missing
        from app.main import create_survey_tables
        create_survey_tables(cls.conn)

        # Cache survey_id and question IDs for convenience
        cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey_row = cls.cursor.fetchone()
        cls.survey_id = survey_row[0]

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
        """Clean up child tables before each test"""
        # DELETE from children first due to FK constraints
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        self.conn.commit()

    def tearDown(self):
        """No need to drop DB; just cleanup after test"""
        pass

    # Example test: verify default survey exists
    def test_default_survey_exists(self):
        self.cursor.execute("SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey[4])  # is_active
        self.assertEqual(survey[2], 'Survey to collect feedback')

    def test_questions_created(self):
        """Verify all questions exist"""
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

# ------------------------
# Survey conducting tests
# ------------------------
    @patch('builtins.input')
    def test_complete_survey_flow(self, mock_input):
        """Full survey submission"""
        mock_input.side_effect = [
            '2023-01-01', '1', 'John Doe', '3', '1', 'Friendly staff', '5'
        ]
        from app.main import conduct_survey
        conduct_survey(self.conn)

        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        self.cursor.execute("SELECT COUNT(*) FROM answers WHERE response_id = ?", (response[0],))
        self.assertEqual(self.cursor.fetchone()[0], 7)

        self.cursor.execute(
            "SELECT answer_value FROM answers WHERE question_id = ? AND response_id = ?",
            (self.questions['What went well during your visit?'], response[0])
        )
        self.assertEqual(self.cursor.fetchone()[0], 'Friendly staff')

    @patch('builtins.input')
    def test_required_field_validation(self, mock_input):
        """Required fields must be provided"""
        mock_input.side_effect = ['', '2023-01-01', '1', 'John', '3', '1', 'Good', '5']
        from app.main import conduct_survey
        conduct_survey(self.conn)
        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    @patch('builtins.input')
    def test_optional_field_handling(self, mock_input):
        """Optional fields can be skipped"""
        mock_input.side_effect = ['2023-01-01', '1', 'John', '3', '1', '', '5']
        from app.main import conduct_survey
        conduct_survey(self.conn)
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)
        self.cursor.execute(
            "SELECT answer_value FROM answers WHERE question_id = ? AND response_id = ?",
            (self.questions['What went well during your visit?'], response[0])
        )
        self.assertEqual(self.cursor.fetchone()[0], '[No response]')

    @patch('builtins.input')
    def test_invalid_multiple_choice_input(self, mock_input):
        """Invalid multiple choice handled"""
        mock_input.side_effect = [
            '2023-01-01', '5', '1', 'John', '3', '1', 'Good', '5'
        ]
        from app.main import conduct_survey
        with patch('builtins.print') as mock_print:
            conduct_survey(self.conn)
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Please enter a number between 1 and 3", output)
        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

# ------------------------
# View responses tests
# ------------------------
    def test_view_empty_responses(self):
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            mock_print.assert_called_with("\nNo responses found in the database.")

    def test_view_multiple_responses(self):
        """View multiple responses"""
        from app.main import view_responses

        # Create 2 responses
        response_ids = []
        for i in range(2):
            self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
            self.cursor.execute("SELECT SCOPE_IDENTITY()")
            new_row = self.cursor.fetchone()
            response_id = int(new_row[0]) if new_row[0] is not None else int(self.cursor.execute("SELECT @@IDENTITY").fetchone()[0])
            response_ids.append(response_id)

        # Add answers
        sample_answers = [
            (response_ids[0], self.questions['Date of visit?'], '2023-01-01'),
            (response_ids[0], self.questions['Which site did you visit?'], 'Princess Alexandra Hospital'),
            (response_ids[1], self.questions['Date of visit?'], '2023-01-02'),
            (response_ids[1], self.questions['Which site did you visit?'], 'Herts & Essex Hospital')
        ]
        for answer in sample_answers:
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                answer
            )
        self.conn.commit()

        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            for rid in response_ids:
                self.assertIn(f"Response ID: {rid}", output)
            self.assertIn("Princess Alexandra Hospital", output)
            self.assertIn("Herts & Essex Hospital", output)

# ------------------------
# Performance test
# ------------------------
    def test_multiple_response_performance(self):
        """Test performance with 100 responses"""
        from app.main import view_responses

        for i in range(100):
            self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
            self.cursor.execute("SELECT SCOPE_IDENTITY()")
            new_row = self.cursor.fetchone()
            response_id = int(new_row[0]) if new_row[0] is not None else int(self.cursor.execute("SELECT @@IDENTITY").fetchone()[0])
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                (response_id, self.questions['Date of visit?'], f'2023-01-{i+1:02d}')
            )
        self.conn.commit()

        start = time.time()
        view_responses(self.conn)
        duration = time.time() - start
        self.assertLess(duration, 1.0, "Viewing responses took too long")


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))
