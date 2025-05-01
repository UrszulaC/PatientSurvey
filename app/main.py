import mysql.connector
from app.config import *
import json
import logging
from datetime import datetime

def create_survey_tables(connection):
    """Create all necessary tables for surveys"""
    try:
        cursor = connection.cursor()
        
        cursor.execute("DROP TABLE IF EXISTS answers")
        cursor.execute("DROP TABLE IF EXISTS responses")
        cursor.execute("DROP TABLE IF EXISTS questions")
        cursor.execute("DROP TABLE IF EXISTS surveys")
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                survey_id INT PRIMARY KEY AUTO_INCREMENT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                question_id INT PRIMARY KEY AUTO_INCREMENT,
                survey_id INT NOT NULL,
                question_text TEXT NOT NULL,
                question_type ENUM('multiple_choice', 'text', 'scale') NOT NULL,
                is_required BOOLEAN DEFAULT FALSE,
                options JSON,
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                response_id INT PRIMARY KEY AUTO_INCREMENT,
                survey_id INT NOT NULL,
                submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS answers (
                answer_id INT PRIMARY KEY AUTO_INCREMENT,
                response_id INT NOT NULL,
                question_id INT NOT NULL,
                answer_value TEXT,
                FOREIGN KEY (response_id) REFERENCES responses(response_id),
                FOREIGN KEY (question_id) REFERENCES questions(question_id)
            )
        """)
        
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
                {'text': 'How easy was finding the department?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Very difficult', 'Difficult', 'Easy', 'Very easy']},
                {'text': 'Were you informed about results timeline?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Yes', 'No']},
                {'text': 'What did we do well?', 'type': 'text', 'required': False},
                {'text': 'How can we improve?', 'type': 'text', 'required': False},
                {'text': 'Overall experience rating?', 'type': 'multiple_choice', 'required': True,
                 'options': ['Very satisfied', 'Somewhat satisfied', 'Neutral', 'Somewhat dissatisfied', 'Very dissatisfied']}
            ]
            
            for q in questions:
                cursor.execute("""
                    INSERT INTO questions (survey_id, question_text, question_type, is_required, options)
                    VALUES (%s, %s, %s, %s, %s)
                """, (
                    survey_id,
                    q['text'],
                    q['type'],
                    q['required'],
                    json.dumps(q['options']) if 'options' in q else None
                ))
        
        connection.commit()
    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        connection.rollback()
    finally:
        cursor.close()

def conduct_survey(connection):
    """Conduct the survey and store responses"""
    try:
        cursor = connection.cursor(dictionary=True)
        
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            print("Survey not found!")
            return

        cursor.execute("""
            SELECT question_id, question_text, question_type, options
            FROM questions WHERE survey_id = %s ORDER BY question_id
        """, (survey['survey_id'],))
        questions = cursor.fetchall()

        print("\n=== Patient Experience Survey ===")
        answers = []
        
        for q in questions:
            print(f"\n{q['question_text']}")
            
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
                        print(f"Please enter 1-{len(options)}")
                    except ValueError:
                        print("Numbers only please")
            else:
                answer = input("Your response: ").strip()
                answers.append({
                    'question_id': q['question_id'],
                    'answer_value': answer if answer else "[No response]"
                })

        cursor.execute("INSERT INTO responses (survey_id) VALUES (%s)", (survey['survey_id'],))
        response_id = cursor.lastrowid
        
        for a in answers:
            cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, %s, %s)
            """, (response_id, a['question_id'], a['answer_value']))
        
        connection.commit()
        print("\nThank you for your feedback!")

    except Exception as e:
        print(f"Error: {e}")
        connection.rollback()
    finally:
        cursor.close()

def view_responses(connection):
    """View all survey responses"""
    try:
        cursor = connection.cursor(dictionary=True)
        
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
        
    except Exception as e:
        print(f"Error viewing responses: {e}")
    finally:
        cursor.close()

def main():
    logging.basicConfig(level=logging.INFO)
    
    try:
        connection = mysql.connector.connect(
            host=HOST,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
        
        create_survey_tables(connection)
        
        while True:
            print("\nMain Menu:")
            print("1. Conduct Survey")
            print("2. View Responses")
            print("3. Exit")
            choice = input("Your choice (1-3): ")
            
            if choice == '1':
                conduct_survey(connection)
            elif choice == '2':
                view_responses(connection)
            elif choice == '3':
                print("Goodbye!")
                break
            else:
                print("Invalid choice")
                
    except mysql.connector.Error as e:
        print(f"Database connection failed: {e}")
    finally:
        if 'connection' in locals() and connection.is_connected():
            connection.close()

if __name__ == "__main__":
    main()