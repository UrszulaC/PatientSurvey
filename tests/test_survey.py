import os
from dotenv import load_dotenv
import unittest
import pyodbc
from unittest.mock import patch, MagicMock
from app.config import Config
from app.utils.db_utils import get_db_connection # Import get_db_connection
import json

# Load .env before using Config for tests
load_dotenv()

class TestPatientSurveySystem(unittest.TestCase):
    def setUp(self):
        try:
            # Connect to existing test DB (assumes it was created once)
            self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
            self.cursor = self.conn.cursor()

            # Clean up data before tests
            tables_to_truncate = [
                "SurveyResponses",
                "SurveyQuestions",
                "PatientSurveys"
            ]
            for table in tables_to_truncate:
                try:
                    self.cursor.execute(f"IF OBJECT_ID('{table}', 'U') IS NOT NULL TRUNCATE TABLE {table}")
                except Exception as e:
                    logging.warning(f"Could not truncate {table}: {e}")

            self.conn.commit()

        except Exception as e:
            logging.error(f"Database setup failed: {e}")
            raise



    @classmethod
    def tearDownClass(cls):
        """Clean up test database"""
        try:
            # Ensure connection exists before trying to close
            if hasattr(cls, 'connection') and cls.connection:
                # Reconnect to master to drop the test database with autocommit=True
                temp_conn = get_db_connection(database_name=None)
                temp_conn.autocommit = True # Explicitly set autocommit to True for DDL
                temp_cursor = temp_conn.cursor()
                temp_cursor.execute(f"IF EXISTS (SELECT name FROM sys.databases WHERE name = '{Config.DB_TEST_NAME}') DROP DATABASE {Config.DB_TEST_NAME}")
                # No explicit commit needed here because autocommit is True
                temp_conn.close()

                # Closes the main connection used by tests if it's still open
                cls.connection.close()
        except pyodbc.Error as e:
            print(f"Warning: Cleanup failed - {e}")
        except Exception as e:
            print(f"Warning: General cleanup failed - {e}")

    def setUp(self):
        """Fresh connection for each test"""
        self.conn = get_db_connection(database_name=Config.DB_TEST_NAME)
        self.cursor = self.conn.cursor()
        # Removed: self.cursor.row_factory = pyodbc.Row # Not supported directly on cursor

        # --- CRITICAL FIX: Use DELETE FROM instead of TRUNCATE TABLE for tables with FK constraints ---
        # Deletes from child tables first, then parent tables
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        
       
        self.conn.commit() # Commit delete operations
        # --- END CRITICAL FIX ---

    def tearDown(self):
        """Cleanup after each test"""
        try:
            if hasattr(self, 'cursor') and self.cursor:
                self.cursor.close()
            if hasattr(self, 'conn') and self.conn: # Check if connection object exists
                self.conn.close()
        except pyodbc.Error as e:
            print(f"Cleanup warning: {e}")
        except Exception as e:
            print(f"Cleanup warning: {e}")

    # --- Database Structure Tests ---

    def test_tables_created_correctly(self):
        """Verify all tables exist with correct structure"""
        # SELECT TABLE_NAME (index 0)
        self.cursor.execute(f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_CATALOG='{Config.DB_TEST_NAME}'")
        tables = {row[0] for row in self.cursor.fetchall()} # Access by index
        self.assertEqual(tables, {'surveys', 'questions', 'responses', 'answers'})

        # Verify surveys table columns
        # SELECT COLUMN_NAME (index 0)
        self.cursor.execute(f"SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'surveys' AND TABLE_CATALOG='{Config.DB_TEST_NAME}'")
        survey_columns = {row[0] for row in self.cursor.fetchall()} # Access by index
        self.assertEqual(survey_columns, {'survey_id', 'title', 'description', 'created_at', 'is_active'})

    def test_default_survey_exists(self):
        """Verify default survey was created"""
        # SELECT * FROM surveys (columns: survey_id, title, description, created_at, is_active)
        # Indices: 0         , 1    , 2          , 3         , 4
        self.cursor.execute("SELECT * FROM surveys WHERE title = ?", ('Patient Experience Survey',)) # Use ?
        survey = self.cursor.fetchone()
        self.assertIsNotNone(survey)
        self.assertTrue(survey[4]) # is_active is at index 4
        self.assertEqual(survey[2], 'Survey to collect feedback') # description is at index 2

    def test_questions_created(self):
        """Verify all questions exist"""
        self.cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (self.survey_id,)) # Use ?
        self.assertEqual(self.cursor.fetchone()[0], 7) # COUNT(*) returns a single value, access by index 0

        # Verify one sample question
        # SELECT question_type (index 0), is_required (index 1), options (index 2)
        self.cursor.execute("""
            SELECT question_type, is_required, options
            FROM questions
            WHERE question_text = ?
        """, ('Which site did you visit?',)) # Use ?
        question = self.cursor.fetchone()
        self.assertEqual(question[0], 'multiple_choice') # question_type is at index 0
        self.assertTrue(question[1]) # is_required is at index 1
        self.assertEqual(json.loads(question[2]), # options is at index 2
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
        conduct_survey(self.conn) # Pass self.conn directly
        # ... rest of the test ...

        # Verify response was created
        # SELECT * FROM responses (response_id is at index 0)
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        # Verify all answers were saved
        self.cursor.execute("SELECT COUNT(*) FROM answers WHERE response_id = ?", (response[0],)) # Access response_id by index
        self.assertEqual(self.cursor.fetchone()[0], 7)

        # Verify specific answers
        # SELECT answer_value (index 0)
        self.cursor.execute("""
            SELECT answer_value FROM answers
            WHERE question_id = ? AND response_id = ?
        """, (self.questions['What went well during your visit?'], response[0])) # Access response_id by index
        self.assertEqual(self.cursor.fetchone()[0], 'Friendly staff') # Access answer_value by index

    @patch('builtins.input')
    def test_required_field_validation(self, mock_input):
        """Test that required fields must be provided"""
        mock_input.side_effect = [
            '',            # Empty date (should reject)
            '2023-01-01', # Valid date
            '1', 'John', '3', '1', 'Good', '5'  # Rest of answers
        ]

        from app.main import conduct_survey
        conduct_survey(self.conn) # Pass self.conn directly

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
        conduct_survey(self.conn) # Pass self.conn directly

        # Verify response was created
        self.cursor.execute("SELECT * FROM responses")
        response = self.cursor.fetchone()
        self.assertIsNotNone(response)

        # Verify optional answer was recorded as empty
        # SELECT answer_value (index 0)
        self.cursor.execute("""
            SELECT answer_value FROM answers
            WHERE question_id = ? AND response_id = ?
        """, (self.questions['What went well during your visit?'], response[0])) # Access response_id by index
        self.assertEqual(self.cursor.fetchone()[0], '[No response]') # Access answer_value by index

    # --- View Responses Tests ---

    def test_view_empty_responses(self):
        """Test viewing when no responses exist"""
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn) # Pass self.conn directly
            mock_print.assert_called_with("\nNo responses found in the database.")

    def test_view_multiple_responses(self):
        """Test viewing multiple responses"""
        # Create test responses
        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,)) # Use ?
        self.cursor.execute("SELECT SCOPE_IDENTITY()")
        new_response_id_row = self.cursor.fetchone()
        if new_response_id_row is None or new_response_id_row[0] is None:
            # Fallback to @@IDENTITY if SCOPE_IDENTITY is None
            self.cursor.execute("SELECT @@IDENTITY")
            new_response_id_row = self.cursor.fetchone()
            if new_response_id_row is None or new_response_id_row[0] is None:
                raise Exception("Failed to retrieve any identity after inserting response.")
        response1 = int(new_response_id_row[0])

        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,)) # Use ?
        self.cursor.execute("SELECT SCOPE_IDENTITY()")
        new_response_id_row = self.cursor.fetchone()
        if new_response_id_row is None or new_response_id_row[0] is None:
            # Fallback to @@IDENTITY if SCOPE_IDENTITY is None
            self.cursor.execute("SELECT @@IDENTITY")
            new_response_id_row = self.cursor.fetchone()
            if new_response_id_row is None or new_response_id_row[0] is None:
                raise Exception("Failed to retrieve any identity after inserting response.")
        response2 = int(new_response_id_row[0])

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
                VALUES (?, ?, ?) -- Use ?
            """, answer)

        self.conn.commit()

        # Test view function
        from app.main import view_responses
        with patch('builtins.print') as mock_print:
            view_responses(self.conn) # Pass self.conn directly

            # Verify responses were displayed
            # The view_responses function itself prints, so we check the printed output
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn(f"Response ID: {response1}", output) # Use f-string
            self.assertIn(f"Response ID: {response2}", output) # Use f-string
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
            conduct_survey(self.conn) # Pass self.conn directly

            # Verify error message was shown
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn("Please enter a number between 1 and 3", output)

        # Verify response was still recorded
        self.cursor.execute("SELECT * FROM responses")
        self.assertIsNotNone(self.cursor.fetchone())

    def test_database_constraints(self):
        """Verify foreign key constraints work"""
        # Try to insert answer with invalid question ID
        with self.assertRaises(pyodbc.Error): # Catch pyodbc.Error
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (?, ?, ?) -- Use ?
            """, (1, 999, 'test'))
            self.conn.commit()

    # --- Performance Tests ---

    def test_multiple_response_performance(self):
        """Test performance with many responses"""
        from app.main import view_responses
        
        # Create 100 test responses
        for i in range(100):
            self.cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (self.survey_id,)) # Use ?
            self.cursor.execute("SELECT SCOPE_IDENTITY()")
            new_response_id_row = self.cursor.fetchone()
            if new_response_id_row is None or new_response_id_row[0] is None:
                self.cursor.execute("SELECT @@IDENTITY")
                new_response_id_row = self.cursor.fetchone()
                if new_response_id_row is None or new_response_id_row[0] is None:
                    raise Exception("Failed to retrieve any identity after inserting response.")
            response_id = int(new_response_id_row[0])

            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (?, ?, ?) -- Use ?
            """, (response_id, self.questions['Date of visit?'], f'2023-01-{i+1:02d}'))

        self.conn.commit()

        # Time the view operation
        import time
        start = time.time()
        view_responses(self.conn) # Pass self.conn directly
        duration = time.time() - start

        self.assertLess(duration, 1.0, "Viewing responses took too long")


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-results'))


