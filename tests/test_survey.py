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

    @classmethod
    def setUpClass(cls):
        """Set up test database and tables"""
        try:
            # Connect to master to create/drop the test database
            # IMPORTANT: Set autocommit=True for DDL operations like CREATE/DROP DATABASE
            cls.connection = get_db_connection(database_name=None)
            cls.connection.autocommit = True # Explicitly set autocommit to True for DDL
            cls.cursor = cls.connection.cursor()

            # SQL Server specific syntax for dropping and creating database
            cls.cursor.execute(f"IF EXISTS (SELECT name FROM sys.databases WHERE name = '{Config.DB_TEST_NAME}') DROP DATABASE {Config.DB_TEST_NAME}")
            cls.cursor.execute(f"CREATE DATABASE {Config.DB_TEST_NAME}")
            # No explicit commit needed here because autocommit is True

            # Close and re-open connection to switch database context to the newly created test DB
            # For subsequent operations on the test database, autocommit can be False (default)
            cls.connection.close()
            cls.connection = get_db_connection(database_name=Config.DB_TEST_NAME)
            cls.connection.autocommit = True # Explicitly set autocommit for this connection
            cls.cursor = cls.connection.cursor()
            # Removed: cls.cursor.row_factory = pyodbc.Row # Not supported directly on cursor

            # Import and call the table creation function from main (needs a connection)
            # This function will now use the pyodbc connection
            from app.main import create_survey_tables
            create_survey_tables(cls.connection) # Pass the connection to it

            # Verify survey exists and has correct questions
            # SELECT survey_id (index 0)
            cls.cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
            survey = cls.cursor.fetchone() # Will be a tuple
            if not survey:
                raise Exception("Default survey not created")

            cls.survey_id = survey[0] # Access by index

            # Store question IDs for tests
            # SELECT question_id (index 0), question_text (index 1)
            cls.cursor.execute("SELECT question_id, question_text FROM questions WHERE survey_id = ? ORDER BY question_id", (cls.survey_id,)) # Use ?
            cls.questions = {row[1]: row[0] for row in cls.cursor.fetchall()} # Access by index: {question_text: question_id}

            if len(cls.questions) < 7:
                raise Exception(f"Expected 7 questions, found {len(cls.questions)}")

        except pyodbc.Error as err: # Catch pyodbc specific errors
            cls.tearDownClass() # Attempt cleanup
            raise Exception(f"Test setup failed (pyodbc error): {err}")
        except Exception as err: # Catch other general exceptions
            cls.tearDownClass() # Attempt cleanup
            raise Exception(f"Test setup failed (general error): {err}")

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

                # Close the main connection used by tests if it's still open
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
        # Delete from child tables first, then parent tables
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        # No need to delete from questions or surveys here, as they are part of the initial setup
        # and are dropped/recreated in setUpClass. setUp only needs to clear transactional data.
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
        conduct_survey(self.conn) # Pass the test connection
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
        conduct_survey(self.conn) # Pass the test connection

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
        conduct_survey(self.conn) # Pass the test connection

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
            view_responses(self.conn) # Pass the test connection
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
            view_responses(self.conn) # Pass the test connection

            # Verify responses were displayed
            # The view_responses function itself prints, so we check the printed output
            output = "\n".join(str(call) for call in mock_print.call_args_list)
            self.assertIn(f"Response ID: {response1}", output) # Use f-string
            self.assertIn(f"Response ID: {response2}", output) # Use f-string
            self.assertIn("Princess Alexandra Hospital", outp
