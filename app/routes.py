from flask import Blueprint, request, jsonify, render_template
import logging
import json
import time
import pyodbc
from app.utils.db_utils import get_db_connection
from app.config import Config
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST, Gauge, Histogram

# Initialize blueprint
main_bp = Blueprint('main', __name__)

# Initialize logging
logger = logging.getLogger(__name__)

# Prometheus metrics - ALL YOUR ORIGINAL METRICS
survey_counter = Counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')
survey_duration = Counter('patient_survey_duration_seconds_total', 'Total time spent completing surveys')
survey_failures = Counter('patient_survey_failures_total', 'Total failed survey submissions')
active_surveys = Counter('active_surveys_total', 'Number of active surveys initialized')
question_count = Counter('survey_questions_total', 'Total number of questions initialized')

# Additional useful metrics for web service
request_duration = Histogram('http_request_duration_seconds', 'HTTP request duration in seconds', ['method', 'endpoint'])
active_connections = Gauge('db_active_connections', 'Number of active database connections')

@main_bp.route('/')
def index():
    """Home page"""
    with request_duration.labels(method='GET', endpoint='/').time():
        return render_template('index.html')

@main_bp.route('/api/survey', methods=['POST'])
def conduct_survey_api():
    """API endpoint to submit a survey"""
    start_time = time.time()
    
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data:
            survey_failures.inc()
            return jsonify({'error': 'No JSON data provided'}), 400
        
        # Connect to database
        conn = get_db_connection(database_name=Config.DB_NAME)
        active_connections.inc()
        cursor = conn.cursor()
        
        # Get survey ID
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            conn.close()
            active_connections.dec()
            survey_failures.inc()
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
                active_connections.dec()
                survey_failures.inc()
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
        active_connections.dec()
        
        # Update metrics
        survey_counter.inc()
        survey_duration.inc(time.time() - start_time)
        
        logger.info(f"New survey response recorded (ID: {response_id})")
        return jsonify({'message': 'Survey submitted successfully', 'response_id': response_id}), 201
        
    except Exception as e:
        survey_failures.inc()
        logger.error(f"Survey submission failed: {e}")
        if 'conn' in locals():
            conn.close()
            active_connections.dec()
        return jsonify({'error': str(e)}), 500

@main_bp.route('/api/responses', methods=['GET'])
def get_responses():
    """API endpoint to get all survey responses"""
    with request_duration.labels(method='GET', endpoint='/api/responses').time():
        try:
            conn = get_db_connection(database_name=Config.DB_NAME)
            active_connections.inc()
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
            active_connections.dec()
            logger.info(f"Retrieved {len(responses)} survey responses")
            return jsonify(responses)
            
        except Exception as e:
            logger.error(f"Failed to retrieve responses: {e}")
            if 'conn' in locals():
                conn.close()
                active_connections.dec()
            return jsonify({'error': str(e)}), 500

@main_bp.route('/api/questions', methods=['GET'])
def get_questions():
    """API endpoint to get survey questions"""
    with request_duration.labels(method='GET', endpoint='/api/questions').time():
        try:
            conn = get_db_connection(database_name=Config.DB_NAME)
            active_connections.inc()
            cursor = conn.cursor()
            
            cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
            survey = cursor.fetchone()
            if not survey:
                conn.close()
                active_connections.dec()
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
            active_connections.dec()
            return jsonify(questions)
            
        except Exception as e:
            logger.error(f"Failed to retrieve questions: {e}")
            if 'conn' in locals():
                conn.close()
                active_connections.dec()
            return jsonify({'error': str(e)}), 500

@main_bp.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection(database_name=Config.DB_NAME)
        active_connections.inc()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        active_connections.dec()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}), 500

@main_bp.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}
