import unittest
import os
import sys
import mysql.connector
import json
from datetime import datetime
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.main import (
    create_survey_tables,
    conduct_survey,
    view_responses
)
from app.config import HOST, USER, PASSWORD, DATABASE

class TestPatientSurveySystem(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.connection = mysql.connector.connect(
            host=HOST,
            user=USER,
            password=PASSWORD,
            database=DATABASE
        )
        # Start with clean slate
        cursor = cls.connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS answers")
        cursor.execute("DROP TABLE IF EXISTS responses")
        cursor.execute("DROP TABLE IF EXISTS questions")
        cursor.execute("DROP TABLE IF EXISTS surveys")
        cls.connection.commit()
        cursor.close()
        
        create_survey_tables(cls.connection)
        
    @classmethod
    def tearDownClass(cls):
        cursor = cls.connection.cursor()
        cursor.execute("DROP TABLE IF EXISTS answers")
        cursor.execute("DROP TABLE IF EXISTS responses")
        cursor.execute("DROP TABLE IF EXISTS questions")
        cursor.execute("DROP TABLE IF EXISTS surveys")
        cls.connection.commit()
        cls.connection.close()
        
    def setUp(self):
        self.cursor = self.connection.cursor(dictionary=True)
        
    def tearDown(self):
        self.cursor.close()

    @patch('builtins.input')
    def test_empty_text_responses(self, mock_input):
        """Test empty answers for text questions"""
        mock_input.side_effect = [
            '',   # Empty date
            '1',  # Site
            '2',  # Ease
            '1',  # Informed
            '',   # Empty "what went well"
            '',   # Empty "how to improve" 
            '3'   # Rating
        ]
        
        conduct_survey(self.connection)
        
        self.cursor.execute("SELECT answer_value FROM answers WHERE question_id = 1")
        answer = self.cursor.fetchone()
        self.assertEqual(answer['answer_value'], "[No response]")

    @patch('builtins.input')
    def test_partial_responses(self, mock_input):
        """Test survey with only required questions answered"""
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        self.connection.commit()
        
        mock_input.side_effect = [
            '2023-01-01',  # Date
            '1',           # Site
            '3',           # Ease
            '1',           # Informed
            '',            # Skip optional
            '',            # Skip optional
            '5'            # Rating
        ]
        
        conduct_survey(self.connection)
        
        self.cursor.execute("SELECT COUNT(*) as count FROM answers")
        count = self.cursor.fetchone()['count']
        self.assertEqual(count, 7)

    def test_response_question_relationship(self):
        """Test foreign key relationship"""
        self.cursor.execute("INSERT INTO responses (survey_id) VALUES (1)")
        response_id = self.cursor.lastrowid
        
        with self.assertRaises(mysql.connector.Error):
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, %s, %s)
            """, (response_id, 999, "Test"))
            self.connection.commit()

    def test_view_responses_with_multiple(self):
        """Test viewing exactly 3 responses"""
        self.cursor.execute("DELETE FROM answers")
        self.cursor.execute("DELETE FROM responses")
        self.connection.commit()
        
        test_dates = [
            "2023-01-01 10:00:00",
            "2023-01-02 11:00:00", 
            "2023-01-03 12:00:00"
        ]
        
        for i, date in enumerate(test_dates):
            self.cursor.execute("""
                INSERT INTO responses (survey_id, submitted_at)
                VALUES (1, %s)
            """, (date,))
            response_id = self.cursor.lastrowid
            
            self.cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (%s, 1, %s)
            """, (response_id, f"Test response {i+1}"))
        
        self.connection.commit()
        
        with patch('builtins.print') as mock_print:
            view_responses(self.connection)
            
            response_count = 0
            for call in mock_print.call_args_list:
                if "Response ID:" in call[0][0]:
                    response_count += 1
            
            self.assertEqual(response_count, 3)

if __name__ == '__main__':
    unittest.main()