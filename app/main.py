import logging
import json
from app.utils.db_utils import with_db_connection
from app.config import Config

from prometheus_client import start_http_server, Counter
import threading

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Prometheus metric
survey_counter = Counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')

def start_prometheus_server():
    start_http_server(8000)  # Prometheus scrapes from http://<host>:8000/metrics

@with_db_connection
def create_survey_tables(conn):
    """Create all necessary tables for surveys"""
    try:
        cursor = conn.cursor()

        # Drop tables in correct order to avoid foreign key constraints
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("DROP TABLE IF EXISTS answers")
        cursor.execute("DROP TABLE IF EXISTS responses")
        cursor.execute("DROP TABLE IF EXISTS questions")
        cursor.execute("DROP TABLE IF EXISTS surveys")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

        # Create tables
        cursor.execute("""
            CREATE TABLE surveys (
                survey_id INT PRIMARY KEY AUTO_INCREMENT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)

        cursor.execute("""
            CREATE TABLE questions (
                question_id INT PRIMARY KEY AUTO_INCREMENT,
                survey_id INT NOT NULL,
                question_text TEXT NOT NULL,
                question_type ENUM('multiple_choice', 'text', 'scale') NOT NULL,
                is_required BOOLEAN DEFAULT FALSE,
                options JSON,
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE responses (
                response_id INT PRIMARY KEY AUTO_INCREMENT,
                survey_id INT NOT NULL,
                submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE answers (
                answer_id INT PRIMARY KEY AUTO_INCREMENT,
                response_id INT NOT NULL,
                question_id INT NOT NULL,
                answer_value TEXT,
                FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
            )
        """)

        # Insert default survey with complete set of questions
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO surveys (title, description, is_active) 
                VALUES ('Patient Experience Survey', 'Survey to collect feedback', TRUE)
            """)
            survey_id = cursor.lastrowid

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
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    survey_id,
                    q['text'],
                    q['type'],
                    q.get('required', False),
                    json.dumps(q['options']) if 'options' in q else None
                ))

        conn.commit()
        logger.info("Database tables initialized successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Database initialization failed: {e}")
        raise

@with_db_connection
def conduct_survey(conn):
    """Conduct the survey and store responses"""
    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            logger.error("Survey not found in database")
            return

        cursor.execute("""
            SELECT question_id, question_text, question_type, is_required, options
            FROM questions WHERE survey_id = %s ORDER BY question_id
        """, (survey['survey_id'],))
        questions = cursor.fetchall()

        print("\n=== Patient Experience Survey ===")
        answers = []

        for q in questions:
            print(f"\n{q['question_text']}{' (required)' if q['is_required'] else ''}")

            if q['question_type'] == 'multiple_choice':
                options = json.loads(q['options'])
                for i, opt in enumerate(options, 1):
                    print(f"{i}. {opt}")
                while True:
                    try:
                        choice = int(input("Your choice (number): "))
                        if 1 <= choice <= len(options):
                            answers.append({
                                'question_id': q['question_id'],
                                'answer_value': options[choice-1]
                            })
                            break
                        print(f"Please enter a number between 1 and {len(options)}")
                    except ValueError:
                        print("Please enter a valid number")
            else:
                while True:
                    answer = input("Your response: ").strip()
                    if answer or not q['is_required']:
                        answers.append({
                            'question_id': q['question_id'],
                            'answer_value': answer if answer else "[No response]"
                        })
                        break
                    print("This field is required")

        cursor.execute("INSERT INTO responses (survey_id) VALUES (%s)", (survey['survey_id'],))
        response_id = cursor.lastrowid

        for a in answers:
            cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, %s, %s)
            """, (response_id, a['question_id'], a['answer_value']))

        conn.commit()
        survey_counter.inc()  # ✅ increment metric
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
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(DISTINCT response_id) as count FROM answers")
        total_responses = cursor.fetchone()['count']

        if total_responses == 0:
            print("\nNo responses found in the database.")
            return

        cursor.execute("""
            SELECT 
                r.response_id,
                DATE_FORMAT(r.submitted_at, '%Y-%m-%d %H:%i') as date,
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
            if row['response_id'] != current_id:
                current_id = row['response_id']
                responses[current_id] = {
                    'date': row['date'],
                    'answers': []
                }
            responses[current_id]['answers'].append(
                (row['question_text'], row['answer_value'])
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
        create_survey_tables()

        while True:
            print("\nMain Menu:")
            print("1. Conduct Survey")
            print("2. View Responses") 
            print("3. Exit")
            choice = input("Your choice (1-3): ")

            if choice == '1':
                conduct_survey()
            elif choice == '2':
                view_responses()
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
