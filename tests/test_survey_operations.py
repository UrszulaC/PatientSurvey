import unittest
import mysql.connector
from app.app import *
from app.config import *
import json

class TestPatientSurveySystem(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.connection = mysql.connector.connect(
            host=HOST,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
        create_survey_tables(cls.connection)
        
    @classmethod
    def tearDownClass(cls):
        cursor = cls.connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS answers")
        cursor.execute("DROP TABLE IF EXISTS responses")
        cursor.execute("DROP TABLE IF EXISTS questions")
        cursor.execute("DROP TABLE IF EXISTS surveys")
        cursor.execute("DROP TABLE IF EXISTS patients")
        cls.connection.close()
        
    def setUp(self):
        # Create test survey
        self.survey_id = create_predefined_survey(self.connection)
        questions = list_questions(self.connection, self.survey_id)
        self.question_ids = [q['question_id'] for q in questions]
        
    def tearDown(self):
        delete_survey(self.connection, self.survey_id)
        
    def test_predefined_survey_creation(self):
        """Test the standard survey is created correctly"""
        survey = get_survey(self.connection, self.survey_id)
        self.assertEqual(survey['title'], "Patient Experience Survey")
        
        questions = list_questions(self.connection, self.survey_id)
        self.assertEqual(len(questions), 7)
        
        # Verify first question
        self.assertEqual(questions[0]['question_text'], "Date of your visit?")
        self.assertEqual(questions[0]['question_type'], "text")
        
        # Verify multiple choice question
        self.assertEqual(questions[1]['question_text'], "Which site did you visit?")
        self.assertEqual(questions[1]['question_type'], "multiple_choice")
        options = json.loads(questions[1]['options'])
        self.assertIn("Princess Alexandra Hospital (Harlow)", options)
        
    def test_patient_survey_flow(self):
        """Test complete survey submission flow"""
        # Simulate patient taking survey
        answers = [
            {"question_id": self.question_ids[0], "answer_value": "2023-07-20"},
            {"question_id": self.question_ids[1], "answer_value": "St Margaret's Hospital (Epping)"},
            {"question_id": self.question_ids[2], "answer_value": "Easy"},
            {"question_id": self.question_ids[3], "answer_value": "Yes"},
            {"question_id": self.question_ids[4], "answer_value": "Friendly staff"},
            {"question_id": self.question_ids[5], "answer_value": "Shorter wait times"},
            {"question_id": self.question_ids[6], "answer_value": "Very satisfied"}
        ]
        
        patient_id = 123
        response_id = submit_response(self.connection, self.survey_id, patient_id, answers)
        self.assertIsNotNone(response_id)
        
        # Verify response was recorded
        response = get_response(self.connection, response_id)
        self.assertEqual(response['patient_id'], patient_id)
        self.assertEqual(len(response['answers']), 7)
        
        # Verify results calculation
        results = get_survey_results(self.connection, self.survey_id)
        self.assertEqual(len(results['responses']), 1)
        
        # Check statistics for rating question
        rating_question = next(
            q for q in results['questions'] 
            if q['question_text'] == "How would you rate your experience?"
        )
        self.assertEqual(rating_question['statistics']['distribution'][0]['answer_value'], "Very satisfied")
        
    # [Additional CRUD tests...]

if __name__ == '__main__':
    unittest.main()