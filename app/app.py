import mysql.connector
from app.config import *
from datetime import datetime
import json
from typing import Optional, Dict, List

# ========== DATABASE SETUP ==========

def create_survey_tables(connection):
    """Create all necessary tables for surveys"""
    try:
        cursor = connection.cursor()
        
        # Surveys table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS surveys (
                survey_id INT PRIMARY KEY AUTO_INCREMENT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE
            )
        """)
        
        # Questions table
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
        
        # Responses table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                response_id INT PRIMARY KEY AUTO_INCREMENT,
                survey_id INT NOT NULL,
                patient_id INT NOT NULL,
                submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id)
            )
        """)
        
        # Answers table
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
        
        # Patients table (for tracking)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS patients (
                patient_id INT PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        connection.commit()
        cursor.close()
        print("Survey tables created successfully")
    except mysql.connector.Error as e:
        print(f"Error creating survey tables: {e}")

# ========== SURVEY CRUD OPERATIONS ==========

def create_survey(connection, title: str, description: str = "") -> Optional[int]:
    """Create a new survey and return the survey ID"""
    try:
        cursor = connection.cursor()
        sql = "INSERT INTO surveys (title, description) VALUES (%s, %s)"
        cursor.execute(sql, (title, description))
        connection.commit()
        return cursor.lastrowid
    except mysql.connector.Error as e:
        print(f"Error creating survey: {e}")
        return None

def create_predefined_survey(connection):
    """Create the standard patient experience survey"""
    survey_id = create_survey(
        connection,
        "Patient Experience Survey",
        "Help us improve our services by sharing your experience"
    )
    
    if not survey_id:
        return None

    # Add all predefined questions
    questions = [
        ("Date of your visit?", "text", True, None),
        ("Which site did you visit?", "multiple_choice", True, [
            "Princess Alexandra Hospital (Harlow)",
            "St Margaret's Hospital (Epping)",
            "Herts & Essex Hospital (Bishop Stortford)"
        ]),
        ("How easy was it to find the department today?", "multiple_choice", True, [
            "Very difficult", "Difficult", "Easy", "Very easy"
        ]),
        ("Were you informed when you will get your results?", "multiple_choice", True, ["Yes", "No"]),
        ("What did we do well?", "text", False, None),
        ("How can we improve?", "text", False, None),
        ("How would you rate your experience?", "multiple_choice", True, [
            "Very satisfied", "Somehow satisfied", "Neither satisfied nor dissatisfied", 
            "Somehow dissatisfied", "Very dissatisfied"
        ])
    ]
    
    for q_text, q_type, required, options in questions:
        add_question(
            connection, survey_id,
            q_text, q_type, required,
            json.dumps(options) if options else None
        )
    
    return survey_id

# [Previous CRUD operations for surveys, questions, responses...]

# ========== ADMIN INTERFACE ==========

def display_admin_menu():
    print("\nAdmin Menu:")
    print("1. Create new blank survey")
    print("2. Create standard patient experience survey")
    print("3. List all surveys")
    print("4. View survey questions")
    print("5. Activate/Deactivate survey")
    print("6. View survey results")
    print("7. Return to main menu")

def admin_menu(connection):
    while True:
        display_admin_menu()
        choice = input("Enter your choice (1-7): ")

        if choice == '1':
            title = input("Enter survey title: ")
            description = input("Enter survey description: ")
            survey_id = create_survey(connection, title, description)
            print(f"Created survey with ID: {survey_id}")
            
        elif choice == '2':
            survey_id = create_predefined_survey(connection)
            if survey_id:
                print(f"Created standard patient experience survey with ID: {survey_id}")
                
        elif choice == '3':
            surveys = list_surveys(connection, active_only=False)
            print("\nAll Surveys:")
            for survey in surveys:
                status = "Active" if survey['is_active'] else "Inactive"
                print(f"{survey['survey_id']}. {survey['title']} ({status})")
                
        elif choice == '4':
            survey_id = int(input("Enter survey ID: "))
            questions = list_questions(connection, survey_id)
            print("\nQuestions:")
            for q in questions:
                print(f"Q{q['question_id']}: {q['question_text']}")
                if q['options']:
                    print(f"  Options: {', '.join(json.loads(q['options']))}")
                    
        elif choice == '5':
            survey_id = int(input("Enter survey ID: "))
            survey = get_survey(connection, survey_id)
            if survey:
                new_status = not survey['is_active']
                update_survey(
                    connection, survey_id,
                    survey['title'], survey['description'],
                    new_status
                )
                print(f"Survey is now {'active' if new_status else 'inactive'}")
                
        elif choice == '6':
            survey_id = int(input("Enter survey ID: "))
            results = get_survey_results(connection, survey_id)
            if results:
                print(f"\nResults for: {results['survey']['title']}")
                for q in results['questions']:
                    print(f"\nQ: {q['question_text']}")
                    if 'statistics' in q:
                        if q['question_type'] == 'scale':
                            print(f"  Average: {q['statistics']['average']:.1f}/10")
                        print("  Responses:")
                        for resp in q['statistics']['distribution']:
                            print(f"  - {resp['answer_value']}: {resp['count']}")
                            
        elif choice == '7':
            break
            
        else:
            print("Invalid choice. Please try again.")

# ========== PATIENT INTERFACE ==========

def take_survey(connection, survey_id, patient_id):
    """Guide patient through completing a survey"""
    survey = get_survey(connection, survey_id)
    if not survey or not survey['is_active']:
        print("Survey not available")
        return

    questions = list_questions(connection, survey_id)
    if not questions:
        print("This survey has no questions")
        return

    print(f"\n{survey['title']}")
    print(survey['description'])
    print("\nPlease answer the following questions:\n")

    answers = []
    for question in questions:
        print(f"\nQ: {question['question_text']}")
        if question['question_type'] == 'multiple_choice':
            options = json.loads(question['options'])
            print("Options:")
            for i, option in enumerate(options, 1):
                print(f"  {i}. {option}")
                
            while True:
                try:
                    choice = int(input("Enter your choice (number): "))
                    if 1 <= choice <= len(options):
                        answers.append({
                            'question_id': question['question_id'],
                            'answer_value': options[choice-1]
                        })
                        break
                    print(f"Please enter a number between 1 and {len(options)}")
                except ValueError:
                    print("Please enter a valid number")
                    
        elif question['question_type'] == 'scale':
            while True:
                try:
                    rating = int(input("Rate from 1-10: "))
                    if 1 <= rating <= 10:
                        answers.append({
                            'question_id': question['question_id'],
                            'answer_value': str(rating)
                        })
                        break
                    print("Please enter a number between 1 and 10")
                except ValueError:
                    print("Please enter a valid number")
                    
        else:  # Text question
            answer = input("Your answer: ")
            if answer or question['is_required']:
                answers.append({
                    'question_id': question['question_id'],
                    'answer_value': answer
                })

    # Submit the response
    response_id = submit_response(connection, survey_id, patient_id, answers)
    if response_id:
        print("\nThank you for completing the survey!")
    else:
        print("\nThere was an error submitting your responses")

# ========== MAIN APPLICATION ==========

def display_main_menu():
    print("\nPatient Survey System")
    print("1. Admin Dashboard")
    print("2. Take a Survey")
    print("3. Exit")

def main():
    try:
        connection = mysql.connector.connect(
            host=HOST,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
        create_survey_tables(connection)
    except mysql.connector.Error as e:
        print(f"Error connecting to database: {e}")
        return

    while True:
        display_main_menu()
        choice = input("Enter your choice (1-3): ")

        if choice == '1':  # Admin
            admin_menu(connection)
            
        elif choice == '2':  # Patient
            surveys = list_surveys(connection)
            print("\nAvailable Surveys:")
            for survey in surveys:
                print(f"{survey['survey_id']}. {survey['title']}")
                
            survey_id = int(input("Enter survey ID to take: "))
            patient_id = int(input("Enter your patient ID: "))
            take_survey(connection, survey_id, patient_id)
            
        elif choice == '3':
            break
            
        else:
            print("Invalid choice. Please try again.")

    connection.close()

if __name__ == "__main__":
    main()