from flask import Blueprint, request, jsonify, render_template
import logging
import json
import time
import pyodbc
from app.utils.db_utils import get_db_connection
from app.config import Config
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

# Initialize blueprint
main_bp = Blueprint('main', __name__)

# Initialize logging
logger = logging.getLogger(__name__)

# Prometheus metrics
survey_counter = Counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')
survey_duration = Counter('patient_survey_duration_seconds_total', 'Total time spent completing surveys')
survey_failures = Counter('patient_survey_failures_total', 'Total failed survey submissions')

@main_bp.route('/')
def index():
    """Home page - could show a menu or redirect to survey"""
    return render_template('index.html')

@main_bp.route('/api/survey', methods=['POST'])
def conduct_survey_api():
    """API endpoint to submit a survey"""
    try:
        start_time = time.time()
        
        # Get JSON data from request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Connect to database
        conn = get_db_connection(database_name=Config.DB_NAME)
        cursor = conn.cursor()
        
        # Get survey ID
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            conn.close()
            return jsonify({'error': 'Survey not found'}), 404
        
        survey_id = survey[0]
        
        # Insert response
        cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (survey_id,))
        conn.commit()
        
        # Get response ID
        cursor.execute("SELECT SCOPE_IDENTITY()")
        response_id_row = cursor.fetchone()
        if response_id_row is None or response_id_row[0] is None:
            cursor.execute("SELECT @@IDENTITY")
            response_id_row = cursor.fetchone()
            if response_id_row is None or response_id_row[0] is None:
                conn.close()
                return jsonify({'error': 'Failed to create response'}), 500
        
        response_id = int(response_id_row[0])
        
        # Insert answers
        for answer in data.get('answers', []):
            cursor.execute("""
                INSERT INTO answers (response_id, question_id, answer_value)
                VALUES (?, ?, ?)
            """, (response_id, answer['question_id'], answer['answer_value']))
        
        conn.commit()
        conn.close()
        
        # Update metrics
        survey_counter.inc()
        survey_duration.inc(time.time() - start_time)
        
        logger.info(f"New survey response recorded (ID: {response_id})")
        return jsonify({'message': 'Survey submitted successfully', 'response_id': response_id}), 201
        
    except Exception as e:
        survey_failures.inc()
        logger.error(f"Survey submission failed: {e}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/responses', methods=['GET'])
def get_responses():
    """API endpoint to get all survey responses"""
    try:
        conn = get_db_connection(database_name=Config.DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT
                r.response_id,
                FORMAT(r.submitted_at, 'yyyy-MM-dd HH:mm') as date,
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
            if row[0] != current_id:
                current_id = row[0]
                responses[current_id] = {
                    'date': row[1],
                    'answers': []
                }
            responses[current_id]['answers'].append({
                'question': row[2],
                'answer': row[3]
            })
        
        conn.close()
        logger.info(f"Retrieved {len(responses)} survey responses")
        return jsonify(responses)
        
    except Exception as e:
        logger.error(f"Failed to retrieve responses: {e}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/questions', methods=['GET'])
def get_questions():
    """API endpoint to get survey questions"""
    try:
        conn = get_db_connection(database_name=Config.DB_NAME)
        cursor = conn.cursor()
        
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            conn.close()
            return jsonify({'error': 'Survey not found'}), 404
        
        cursor.execute("""
            SELECT question_id, question_text, question_type, is_required, options
            FROM questions WHERE survey_id = ? ORDER BY question_id
        """, (survey[0],))
        
        questions = []
        for q in cursor.fetchall():
            question = {
                'question_id': q[0],
                'question_text': q[1],
                'question_type': q[2],
                'is_required': bool(q[3]),
                'options': json.loads(q[4]) if q[4] else []
            }
            questions.append(question)
        
        conn.close()
        return jsonify(questions)
        
    except Exception as e:
        logger.error(f"Failed to retrieve questions: {e}")
        return jsonify({'error': str(e)}), 500

@main_bp.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
