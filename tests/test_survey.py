import os
import unittest
import pyodbc
import logging
from dotenv import load_dotenv
from unittest.mock import patch
from app.config import Config
from app.utils.db_utils import get_db_connection
import json

# Load .env before using Config for tests
load_dotenv()

class TestPatientSurveySystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Set up once for all tests"""
        cls.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        cls.cursor = cls.conn.cursor()

        # Fetch survey_id and question IDs for convenience
        cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
        survey_row = cls.cursor.fetchone()
        if survey_row:
            cls.survey_id = survey_row[0]
        else:
            raise Exception("Default survey not found in test DB")

        # Map questions for easy access in tests
        cls.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ?", (cls.survey_id,))
        cls.questions = {row[1]: row[0] for row in cls.cursor.fetchall()}

    def setUp(self):
        """Clean tables before each test (child → parent)"""
        try:
            self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            self.cursor = self.conn.cursor()

            # Delete child tables first to satisfy FK constraints
            self.cursor.execute("DELETE FROM answers")
            self.cursor.execute("DELETE FROM responses")
            self.conn.commit()
        except Exception as e:
            logging.error(f"Database setup failed: {e}")
            raise

    def tearDown(self):
        """Close connection after each test"""
        try:
            if hasattr(self, 'cursor') and self.cursor:
                self.cursor.close()
            if hasattr(self, 'conn') and self.conn:
                self.conn.close()
        except Exception as e:
            logging.warning(f"Cleanup warning: {e}")

    # ------------------------
    # Database structure tests
    # ------------------------
    def test_tables_created_correctly(self):
        """Verify all tables exist with correct structure"""
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
        self.assertTrue(survey[4])  # is_active
        self.assertEqual(survey[2], 'Survey to collect feedback')  # description

    def test_questions_created(self):
        """Verify all questions exist"""
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,))
        self.assertEqual(self.cursor.fetchone()[0], 7)

# ------------------------
# Survey conducting tests
# ------------------------
    @patch('builtins.input')
    def test_complete_survey_flow(self, mock_input):
        """Test full survey submission with all answers"""
        mock_input.side_effect = [
            '2023-01-01', '1', 'John Doe', '3', '1', 'Friendly staff', '5'
        ]
        from app.main import conduct_survey
        conduct_survey(self.conn)

        # Verify response created
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        # Verify all answers saved
        self.cursor.execute("SELECT COUNT(*) FROM answers WHERE response_id = ?", (response[0],))
        self.assertEqual(self.cursor.fetchone()[0], 7)

        # Verify optional answer recorded correctly
        self.cursor.execute(
            "SELECT answer_value FROM answers WHERE question_id = ? AND response_id = ?",
            (self.questions['What went well during your visit?'], response[0])
        )
        self.assertEqual(self.cursor.fetchone()[0], 'Friendly staff')

    @patch('builtins.input')
    def test_required_field_validation(self, mock_input):
        """Test that required fields must be provided"""
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

# ------------------------
# View responses tests
# ------------------------
    def test_view_empty_responses(self):
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn)
            mock_print.assert_called_with("\nNo responses found in the database.")

if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))



