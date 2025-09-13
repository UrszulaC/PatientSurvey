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

class TestPatientSurveySystem(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Set up once for all tests"""
        cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        cls.cursor = cls.conn.cursor()

        # Fetch survey_id and question IDs
        cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey_row = cls.cursor.fetchone()
        if survey_row:
            cls.survey_id = survey_row[0]
        else:
            raise Exception("Default survey not found in test DB")

        # Map questions for easy access
        cls.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (cls.survey_id,))
        cls.questions = {row[1]: row[0] for row in cls.cursor.fetchall()}

    def setUp(self):
        """Clean child tables before each test"""
        self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        self.cursor = self.conn.cursor()
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        self.conn.commit()

    def tearDown(self):
        """Close connection after each test"""
        if hasattr(self, 'cursor') and self.cursor:
            self.cursor.close()
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

    # ------------------------
    # Database structure tests
    # ------------------------
    def test_tables_created_correctly(self):
        """Verify all tables exist"""
        self.cursor.execute(
            f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE='BASE TABLE' AND TABLE_CATALOG='{Config.DB_TEST_NAME}'"
        )
        tables = {row[0] for row in self.cursor.fetchall()}
        self.assertEqual(tables, {'surveys', 'questions', 'responses', 'answers'})

    def test_default_survey_exists(self):
        """Verify default survey was created"""
        self.cursor.execute("SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey[4])
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
