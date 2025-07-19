import logging
import json
import time

import pyodbc
from app.utils.db_utils import get_db_connection # Imports get_db_connection directly
from app.config import Config

from prometheus_client import start_http_server, Counter
import threading

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metrics
survey_counter = Counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')
survey_duration = Counter('patient_survey_duration_seconds_total', 'Total time spent completing surveys')
survey_failures = Counter('patient_survey_failures_total', 'Total failed survey submissions')
active_surveys = Counter('active_surveys_total', 'Number of active surveys initialized')
question_count = Counter('survey_questions_total', 'Total number of questions initialized')


# This function needs to handle its own connection for creating/dropping databases
# because the decorator connects to a specific database.
# it will take `conn` as an argument, and `main()` will pass it.
def create_survey_tables(conn):
    """Create all necessary tables for surveys"""
    try:
        cursor = conn.cursor()

        # SQL Server specific syntax for dropping tables in correct order
        # No SET FOREIGN_KEY_CHECKS in SQL Server. Drop tables directly.
        # Use IF OBJECT_ID to check existence before dropping
        cursor.execute("IF OBJECT_ID('answers', 'U') IS NOT NULL DROP TABLE answers")
        cursor.execute("IF OBJECT_ID('responses', 'U') IS NOT NULL DROP TABLE responses")
        cursor.execute("IF OBJECT_ID('questions', 'U') IS NOT NULL DROP TABLE questions")
        cursor.execute("IF OBJECT_ID('surveys', 'U') IS NOT NULL DROP TABLE surveys")

        # Create tables with SQL Server syntax
        cursor.execute("""
            CREATE TABLE surveys (
                survey_id INT IDENTITY(1,1) PRIMARY KEY, -- SQL Server AUTO_INCREMENT
                title NVARCHAR(255) NOT NULL,            -- NVARCHAR for VARCHAR
                description NVARCHAR(MAX),               -- TEXT equivalent
                created_at DATETIME DEFAULT GETDATE(),   -- SQL Server CURRENT_TIMESTAMP
                is_active BIT DEFAULT 1                  -- SQL Server BOOLEAN
            )
        """)

        cursor.execute("""
            CREATE TABLE questions (
                question_id INT IDENTITY(1,1) PRIMARY KEY,
                survey_id INT NOT NULL,
                question_text NVARCHAR(MAX) NOT NULL,
                question_type NVARCHAR(50) NOT NULL,     -- ENUM equivalent (VARCHAR with CHECK constraint if needed)
                is_required BIT DEFAULT 0,
                options NVARCHAR(MAX),                   -- JSON equivalent
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE responses (
                response_id INT IDENTITY(1,1) PRIMARY KEY,
                survey_id INT NOT NULL,
                submitted_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE answers (
                answer_id INT IDENTITY(1,1) PRIMARY KEY,
                response_id INT NOT NULL,
                question_id INT NOT NULL,
                answer_value NVARCHAR(MAX),
                FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
            )
        """)

        # Default survey with complete set of questions
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO surveys (title, description, is_active)
                VALUES (?, ?, ?) -- Use ? for pyodbc parameters
            """, ('Patient Experience Survey', 'Survey to collect feedback', True))
            # Get last inserted ID for pyodbc (SCOPE_IDENTITY() or @@IDENTITY)
            cursor.execute("SELECT SCOPE_IDENTITY()")
            survey_id = int(cursor.fetchone()[0]) # SCOPE_IDENTITY returns decimal, cast to int
            active_surveys.inc()

            questions = [
                {'text': 'Date of visit?', 'type': 'text', 'required': True},
                {'text': 'Which site did you visit?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Princess Alexandra Hospital', 'St Margaret\'s Hospital', 'Herts & Essex Hospital']},
                {'text': 'Patient name?', 'type': 'text', 'required': True},
                {'text': 'How easy was it to get an appointment?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Very difficult', 'Somewhat difficult', 'Neutral', 'Easy', 'Very easy']},
                {'text': 'Were you properly informed about your procedure?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Yes', 'No', 'Partially']},
                {'text': 'What went well during your visit?', 'type': 'text', 'required': False},
                {'text': 'Overall satisfaction (1-5)', 'type': 'multiple_choice', 'required': True,
                 'options': ['1', '2', '3', '4', '5']}
            ]

            for q in questions:
                cursor.execute("""
                    INSERT INTO questions (survey_id, question_text, question_type, is_required, options)
                    VALUES (?, ?, ?, ?, ?) -- Use ? for pyodbc parameters
                """, (
                    survey_id,
                    q['text'],
                    q['type'],
                    q.get('required', False), # Boolean True/False maps to BIT 1/0
                    json.dumps(q['options']) if 'options' in q else None
                ))
            question_count.inc(len(questions))

        conn.commit() # Explicit commit for DDL and DML
        logger.info("Database tables initialized successfully")

    except pyodbc.Error as e: # Catch pyodbc specific errors
        survey_failures.inc()
        conn.rollback()
        logger.error(f"Database initialization failed: {e}")
        raise
    except Exception as e: # Catch other general errors
        survey_failures.inc()
        conn.rollback()
        logger.error(f"General initialization failed: {e}")
        raise

# Decorator used for conduct_survey and view_responses
@with_db_connection
def conduct_survey(conn):
    """Conduct the survey and store responses"""
    try:
        start_time = time.time()  # Starting timer
        # For dictionary-like access, pyodbc cursors need row_factory or manual mapping
        cursor = conn.cursor()
        cursor.row_factory = pyodbc.Row # This makes rows behave like dictionaries

        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            logger.error("Survey not found in database")
            return

        cursor.execute("""
            SELECT question_id, question_text, question_type, is_required, options
            FROM questions WHERE survey_id = ? ORDER BY question_id -- Use ? for parameters
        """, (survey.survey_id,)) # Access by attribute if using pyodbc.Row

        questions = cursor.fetchall()

        print("\n=== Patient Experience Survey ===")
        answers = []

        for q in questions:
            print(f"\n{q.question_text}{' (required)' if q.is_required else ''}") # Access by attribute

            if q.question_type == 'multiple_choice':
                options = json.loads(q.options)
                for i, opt in enumerate(options, 1):
                    print(f"{i}. {opt}")
                while True:
                    try:
                        choice = int(input("Your choice (number): "))
                        if 1 <= choice <= len(options):
                            answers.append({
                                'question_id': q.question_id,
                                'answer_value': options[choice-1]
                            })
                            break
                        print(f"Please enter a number between 1 and {len(options)}")
                    except ValueError:
                        print("Please enter a valid number")
            else:
                while True:
                    answer = input("Your response: ").strip()
                    if answer or not q.is_required:
                        answers.append({
                            'question_id': q.question_id,
                            'answer_value': answer if answer else "[No response]"
                        })
                        break
                    print("This field is required")

        cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (survey.survey_id,)) # Use ?
        cursor.execute("SELECT SCOPE_IDENTITY()") # Get last inserted ID
        response_id = int(cursor.fetchone()[0])

        for a in answers:
            cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (?, ?, ?) -- Use ?
            """, (response_id, a['question_id'], a['answer_value']))

        conn.commit() # Explicit commit
        survey_counter.inc()  # increment metric
        survey_duration.inc(time.time() - start_time)  # record time spent
        print("\nThank you for your feedback!")
        logger.info(f"New survey response recorded (ID: {response_id})")

    except Exception as e:
        conn.rollback()
        logger.error(f"Survey submission failed: {e}")
        raise

@with_db_connection
def view_responses(conn):
    """View all survey responses"""
    try:
        cursor = conn.cursor()
        cursor.row_factory = pyodbc.Row # For dictionary-like access

        cursor.execute("SELECT COUNT(DISTINCT response_id) as count FROM answers")
        total_responses = cursor.fetchone().count # Access by attribute if using pyodbc.Row

        if total_responses == 0:
            print("\nNo responses found in the database.")
            return

        cursor.execute("""
            SELECT
                r.response_id,
                FORMAT(r.submitted_at, 'yyyy-MM-dd HH:mm') as date, -- SQL Server FORMAT function
                q.question_text,
                a.answer_value
            FROM responses r
            JOIN answers a ON r.response_id = a.response_id
            JOIN questions q ON a.question_id = q.question_id
            ORDER BY r.response_id, q.question_id
        """)

        responses = {}
        current_id = None

        for row in cursor.fetchall():
            if row.response_id != current_id: # Access by attribute
                current_id = row.response_id
                responses[current_id] = {
                    'date': row.date,
                    'answers': []
                }
            responses[current_id]['answers'].append(
                (row.question_text, row.answer_value) # Access by attribute
            )

        print(f"\n=== SURVEY RESPONSES ({len(responses)} total) ===")
        for response_id, data in responses.items():
            print(f"\nResponse ID: {response_id} | Date: {data['date']}")
            print("-" * 50)
            for question, answer in data['answers']:
                print(f"Q: {question}")
                print(f"A: {answer}\n")
            print("-" * 50)

        logger.info(f"Viewed {len(responses)} survey responses")

    except Exception as e:
        logger.error(f"Failed to retrieve responses: {e}")
        raise

def main():
    try:
        logger.info("Starting Patient Survey Application")
        # Start metrics server
        threading.Thread(target=start_http_server, args=(8000,), daemon=True).start()

        # Get a connection for DDL operations in create_survey_tables
        # This connection should not specify a database initially
        conn_for_ddl = get_db_connection(database_name=None)
        
        # Drop and create the main application database first
        # This requires connecting to master database
        cursor_ddl = conn_for_ddl.cursor()
        cursor_ddl.execute(f"IF EXISTS (SELECT name FROM sys.databases WHERE name = '{Config.DB_NAME}') DROP DATABASE {Config.DB_NAME}")
        cursor_ddl.execute(f"CREATE DATABASE {Config.DB_NAME}")
        conn_for_ddl.commit()
        cursor_ddl.close()
        conn_for_ddl.close() # Close the DDL connection

        # Create tables within the newly created Config.DB_NAME database
        # This connection will be passed to create_survey_tables
        conn_for_tables = get_db_connection(database_name=Config.DB_NAME)
        create_survey_tables(conn_for_tables) # Pass connection to decorator
        conn_for_tables.close() # Close after use

        while True:
            print("\nMain Menu:")
            print("1. Conduct Survey")
            print("2. View Responses")
            print("3. Exit")
            choice = input("Your choice (1-3): ")

            if choice == '1':
                # The decorator @with_db_connection will handle the connection for conduct_survey
                conduct_survey(db_name=Config.DB_NAME) # Pass db_name to decorator
            elif choice == '2':
                # The decorator @with_db_connection will handle the connection for view_responses
                view_responses(db_name=Config.DB_NAME) # Pass db_name to decorator
            elif choice == '3':
                print("Goodbye!")
                break
            else:
                print("Please enter a number between 1 and 3")

    except Exception as e:
        logger.critical(f"Application error: {e}")
    finally:
        logger.info("Application shutdown")

if __name__ == "__main__":
    main()
