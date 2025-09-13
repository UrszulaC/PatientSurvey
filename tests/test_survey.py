import os
import unittest
import logging
import pyodbc
import json
import time
from unittest.mock import patch
from dotenv import load_dotenv
from app.config import Config
from app.utils.db_utils import get_db_connection

# Load .env before using Config
load_dotenv()

class TestPatientSurveySystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Connect to the test database and prepare survey and questions mapping."""
        try:
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

    # --- Database Structure Tests ---
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

    # --- Survey Conducting Tests ---
    @patch('builtins.input')
    def test_complete_survey_flow(self, mock_input):
        mock_input.side_effect = [
            '2023-01-01',
            '1',
            'John Doe',
            '3',
            '1',
            'Friendly staff',
            '5'
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
        mock_input.side_effect = [
            '', '2023-01-01', '1', 'John', '3', '1', 'Good', '5'
        ]
        from app.main import conduct_survey
        conduct_survey(self.conn)

        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    @patch('builtins.input')
    def test_optional_field_handling(self, mock_input):
        mock_input.side_effect = [
            '2023-01-01', '1', 'John', '3', '1', '', '5'
        ]
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

    # --- View Responses Tests ---
    def test_view_empty_responses(self):
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            mock_print.assert_any_call("\nNo responses found in the database.")

    def test_view_multiple_responses(self):
        # Insert two responses
        for _ in range(2):
            self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,))
            self.cursor.execute("SELECT SCOPE_IDENTITY()")
            new_response_row = self.cursor.fetchone()
            if not new_response_row or new_response_row[0] is None:
                self.cursor.execute("SELECT @@IDENTITY")
                new_response_row = self.cursor.fetchone()
            response_id = int(new_response_row[0])
            # Insert an answer for testing
            self.cursor.execute(
                "INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                (response_id, self.questions['Date of visit?'], f'2023-01-{response_id:02d}')
            )
        self.conn.commit()

        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Date of visit?", output)

    # --- Edge Cases ---
    @patch('builtins.input')
    def test_invalid_multiple_choice_input(self, mock_input):
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
