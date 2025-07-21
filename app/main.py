
import logging
import json
import time
import pyodbc
from app.utils.db_utils import get_db_connection # Import get_db_connection directly
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
# We'll modify it to take `conn` as an argument, and `main()` will pass it.
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
                -- CRITICAL FIX: Explicitly set ON DELETE NO ACTION to resolve cascade path ambiguity
                FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE NO ACTION
            )
        """)

        # REMOVED CRITICAL FIX: Grant permissions to the DB_USER on the newly created database
        # This is removed because the DB_USER (adminuser) is the server admin and implicitly
        # becomes the dbo of the newly created database, making these explicit grants redundant
        # and causing the "login already has an account with the user name 'dbo'" error.
        # cursor.execute(f"IF NOT EXISTS (SELECT * FROM sys.database_principals WHERE name = '{Config.DB_USER}') CREATE USER [{Config.DB_USER}] FOR LOGIN [{Config.DB_USER}]")
        # cursor.execute(f"ALTER ROLE db_owner ADD MEMBER [{Config.DB_USER}]") # Grant db_owner for simplicity during debug


        survey_id = None # Initialize survey_id

        # Check if default survey exists
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        existing_survey_row = cursor.fetchone() # Fetch the row if it exists

        if existing_survey_row:
            survey_id = existing_survey_row[0] # Use existing ID
            logger.info("Default survey already exists.")
        else:
            # Insert default survey
            logger.info("Attempting to insert default survey...")
            cursor.execute("""
                INSERT INTO surveys (title, description, is_active)
                VALUES (?, ?, ?) -- Use ? for pyodbc parameters
            """, ('Patient Experience Survey', 'Survey to collect feedback', True))
            
            # Check if the insert actually happened
            if cursor.rowcount == 0:
                raise Exception("Insert into surveys table failed: No rows were inserted. Check for hidden constraints or transaction issues.")

            # Get last inserted ID for pyodbc (SCOPE_IDENTITY() or @@IDENTITY)
            # Use @@IDENTITY as a fallback if SCOPE_IDENTITY() is still problematic in this environment
            cursor.execute("SELECT SCOPE_IDENTITY()")
            new_survey_id_row = cursor.fetchone()
            
            print(f"DEBUG: new_survey_id_row from SCOPE_IDENTITY(): {new_survey_id_row}")
            
            if new_survey_id_row is None or new_survey_id_row[0] is None: # Check for None row or None value
                # Fallback to @@IDENTITY if SCOPE_IDENTITY is None
                logger.warning("SCOPE_IDENTITY returned None. Attempting to use @@IDENTITY as a fallback.")
                cursor.execute("SELECT @@IDENTITY")
                new_survey_id_row = cursor.fetchone()
                print(f"DEBUG: new_survey_id_row from @@IDENTITY(): {new_survey_id_row}")
                if new_survey_id_row is None or new_survey_id_row[0] is None:
                    raise Exception("Failed to retrieve any identity after inserting survey. Insert might have failed or returned no ID.")
            
            survey_id = int(new_survey_id_row[0]) # Convert to int
            active_surveys.inc()
            logger.info(f"Default survey created with ID: {survey_id}")

            # Insert questions only if the survey was just created
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

        # Ensure survey_id is set before proceeding
        if survey_id is None:
            raise Exception("Failed to determine survey_id for Patient Experience Survey.")

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

# Removed @with_db_connection decorator
def conduct_survey(conn): # Now explicitly accepts conn
    """Conduct the survey and store responses"""
    try:
        start_time = time.time()  # Starting timer
        cursor = conn.cursor()
        # Removed: cursor.row_factory = pyodbc.Row # Not supported directly on cursor

        # SELECT survey_id (index 0)
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            logger.error("Survey not found in database")
            return

        # SELECT question_id (0), question_text (1), question_type (2), is_required (3), options (4)
        cursor.execute("""
            SELECT question_id, question_text, question_type, is_required, options
            FROM questions WHERE survey_id = ? ORDER BY question_id -- Use ? for parameters
        """, (survey[0],)) # Access survey_id by index

        questions = cursor.fetchall()

        print("\n=== Patient Experience Survey ===")
        answers = []

        for q in questions:
            print(f"\n{q[1]}{' (required)' if q[3] else ''}") # Access question_text by index (1), is_required by index (3)

            if q[2] == 'multiple_choice': # question_type is at index 2
                options = json.loads(q[4]) if q[4] is not None else [] # options is at index 4
                for i, opt in enumerate(options, 1):
                    print(f"{i}. {opt}")
                while True:
                    try:
                        choice = int(input("Your choice (number): "))
                        if 1 <= choice <= len(options):
                            answers.append({
                                'question_id': q[0], # question_id is at index 0
                                'answer_value': options[choice-1]
                            })
                            break
                        print(f"Please enter a number between 1 and {len(options)}")
                    except ValueError:
                        print("Please enter a valid number")
            else:
                while True:
                    answer = input("Your response: ").strip()
                    if answer or not q[3]: # is_required is at index 3
                        answers.append({
                            'question_id': q[0], # question_id is at index 0
                            'answer_value': answer if answer else "[No response]"
                        })
                        break
                    print("This field is required")

        cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (survey[0],)) # Access survey_id by index
        cursor.execute("SELECT SCOPE_IDENTITY()") # Get last inserted ID
        new_response_id_row = cursor.fetchone()
        
        # CRITICAL FIX: Add robust check and fallback for SCOPE_IDENTITY in conduct_survey
        if new_response_id_row is None or new_response_id_row[0] is None:
            logger.warning("SCOPE_IDENTITY returned None in conduct_survey. Attempting to use @@IDENTITY as a fallback.")
            cursor.execute("SELECT @@IDENTITY")
            new_response_id_row = cursor.fetchone()
            if new_response_id_row is None or new_response_id_row[0] is None:
                raise Exception("Failed to retrieve any identity after inserting response in conduct_survey. Insert might have failed or returned no ID.")
        
        response_id = int(new_response_id_row[0]) # Convert to int


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

# Removed @with_db_connection decorator
def view_responses(conn): # Now explicitly accepts conn
    """View all survey responses"""
    try:
        cursor = conn.cursor()
        # Removed: cursor.row_factory = pyodbc.Row # Not supported directly on cursor

        # SELECT COUNT(DISTINCT response_id) as count (index 0)
        cursor.execute("SELECT COUNT(DISTINCT response_id) as count FROM answers")
        total_responses = cursor.fetchone()[0] # Access count by index

        if total_responses == 0:
            print("\nNo responses found in the database.")
            return

        # SELECT r.response_id (0), date (1), q.question_text (2), a.answer_value (3)
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
            if row[0] != current_id: # Access response_id by index
                current_id = row[0]
                responses[current_id] = {
                    'date': row[1], # Access date by index
                    'answers': []
                }
            responses[current_id]['answers'].append(
                (row[2], row[3]) # Access question_text by index (2), answer_value by index (3)
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
        conn_for_ddl.autocommit = True # Explicitly set autocommit to True for DDL
        
        # Drop and create the main application database first
        # This requires connecting to master database
        cursor_ddl = conn_for_ddl.cursor()
        cursor_ddl.execute(f"IF EXISTS (SELECT name FROM sys.databases WHERE name = '{Config.DB_NAME}') DROP DATABASE {Config.DB_NAME}")
        cursor_ddl.execute(f"CREATE DATABASE {Config.DB_NAME}")
        # No explicit commit needed here because autocommit is True
        cursor_ddl.close()
        conn_for_ddl.close() # Close the DDL connection

        # Now, create tables within the newly created Config.DB_NAME database
        # This connection will be passed to create_survey_tables
        conn_for_tables = get_db_connection(database_name=Config.DB_NAME)
        conn_for_tables.autocommit = True # Explicitly set autocommit for this connection
        create_survey_tables(conn_for_tables) # Pass connection to decorator
        conn_for_tables.close() # Close after use

        # Main application loop will now manage its own connection
        app_conn = get_db_connection(database_name=Config.DB_NAME) # NEW: Get a dedicated connection for the app
        # app_conn.autocommit = False # Default behavior for DML operations

        while True:
            print("\nMain Menu:")
            print("1. Conduct Survey")
            print("2. View Responses")
            print("3. Exit")
            choice = input("Your choice (1-3): ")

            if choice == '1':
                conduct_survey(app_conn) # Pass the app_conn
            elif choice == '2':
                view_responses(app_conn) # Pass the app_conn
            elif choice == '3':
                print("Goodbye!")
                break
            else:
                print("Please enter a number between 1 and 3")

    except Exception as e:
        logger.critical(f"Application error: {e}")
    finally:
        if 'app_conn' in locals() and app_conn: # Ensure app_conn is defined and not None
            app_conn.close() # Close app connection on exit
        logger.info("Application shutdown")

if __name__ == "__main__":
    main()
