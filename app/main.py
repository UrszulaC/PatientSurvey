import os
import logging
import json
import time
import pyodbc
from flask import Flask, request, jsonify, render_template
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST, Gauge, Histogram
from app.utils.db_utils import get_db_connection
from app.config import Config

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__, template_folder='../templates')

# Prometheus metrics
def get_or_create_counter(name, description, registry=None):
    try:
        return Counter(name, description, registry=registry)
    except ValueError:
        # Metric already exists, return the existing one
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

def get_or_create_histogram(name, description, labelnames=(), registry=None):
    try:
        return Histogram(name, description, labelnames=labelnames, registry=registry)
    except ValueError:
        # Metric already exists, return the existing one
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

def get_or_create_gauge(name, description, registry=None):
    try:
        return Gauge(name, description, registry=registry)
    except ValueError:
        # Metric already exists, return the existing one
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

survey_counter = get_or_create_counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')
survey_duration = get_or_create_counter('patient_survey_duration_seconds_total', 'Total time spent completing surveys')
survey_failures = get_or_create_counter('patient_survey_failures_total', 'Total failed survey submissions')
active_surveys = get_or_create_counter('active_surveys_total', 'Number of active surveys initialized')
question_count = get_or_create_counter('survey_questions_total', 'Total number of questions initialized')

# Additional metrics for web service
request_duration = get_or_create_histogram('http_request_duration_seconds', 'HTTP request duration in seconds', ['method', 'endpoint'])
active_connections = get_or_create_gauge('db_active_connections', 'Number of active database connections')

def create_survey_tables(conn):
    """Create all necessary tables for surveys safely (if not exist)"""
    try:
        cursor = conn.cursor()

        # Create surveys table
        cursor.execute("""
            IF OBJECT_ID('surveys', 'U') IS NULL
            CREATE TABLE surveys (
                survey_id INT IDENTITY(1,1) PRIMARY KEY,
                title NVARCHAR(255) NOT NULL,
                description NVARCHAR(MAX),
                created_at DATETIME DEFAULT GETDATE(),
                is_active BIT DEFAULT 1
            )
        """)

        # Create questions table
        cursor.execute("""
            IF OBJECT_ID('questions', 'U') IS NULL
            CREATE TABLE questions (
                question_id INT IDENTITY(1,1) PRIMARY KEY,
                survey_id INT NOT NULL,
                question_text NVARCHAR(MAX) NOT NULL,
                question_type NVARCHAR(50) NOT NULL,
                is_required BIT DEFAULT 0,
                options NVARCHAR(MAX),
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        # Create responses table
        cursor.execute("""
            IF OBJECT_ID('responses', 'U') IS NULL
            CREATE TABLE responses (
                response_id INT IDENTITY(1,1) PRIMARY KEY,
                survey_id INT NOT NULL,
                submitted_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

        # Create answers table
        cursor.execute("""
            IF OBJECT_ID('answers', 'U') IS NULL
                CREATE TABLE answers (
                answer_id INT IDENTITY(1,1) PRIMARY KEY,
                response_id INT NOT NULL,
                question_id INT NOT NULL,
                answer_value NVARCHAR(MAX),
                FOREIGN KEY (response_id) REFERENCES responses(response_id) ON DELETE CASCADE,
                FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE NO ACTION
            )
        """)

        # Insert default survey if it doesn't exist
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()

        if not survey:
            cursor.execute("""
                INSERT INTO surveys (title, description, is_active)
                VALUES (?, ?, ?)
            """, ('Patient Experience Survey', 'Survey to collect feedback', True))
            conn.commit()

            # Try to get survey_id from SCOPE_IDENTITY first
            survey_id_row = cursor.execute("SELECT SCOPE_IDENTITY()").fetchone()
            if survey_id_row is None or survey_id_row[0] is None:
                # Fallback: query the row directly
                cursor.execute("SELECT survey_id FROM surveys WHERE title = ?", ('Patient Experience Survey',))
                survey_id_row = cursor.fetchone()
                if survey_id_row is None:
                    raise Exception("Failed to create or retrieve default survey in create_survey_tables")

            survey_id = int(survey_id_row[0])
            active_surveys.inc()  # Increment active surveys metric
        else:
            survey_id = survey[0]

        # Insert default questions only if they do not exist
        cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (survey_id,))
        existing_questions = cursor.fetchone()[0]
        
        if existing_questions == 0:
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
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    survey_id,
                    q['text'],
                    q['type'],
                    q.get('required', False),
                    json.dumps(q['options']) if 'options' in q else None
                ))
                question_count.inc()  # Increment question count metric

        conn.commit()
        logger.info("Database tables initialized safely.")

    except Exception as e:
        survey_failures.inc()
        conn.rollback()
        logger.error(f"Database initialization failed: {e}")
        raise

def initialize_database():
    """Initialize the database tables"""
    try:
        # Get connection for DDL operations
        conn = get_db_connection(database_name=None)
        conn.autocommit = True
        
        cursor = conn.cursor()
        
        # Check if database exists
        cursor.execute(
            "SELECT name FROM sys.databases WHERE name = ?", 
            (Config.DB_NAME,)
        )
        db_exists = cursor.fetchone()
        
        if not db_exists:
            cursor.execute(f"CREATE DATABASE [{Config.DB_NAME}]")
            logger.info(f"Created database: {Config.DB_NAME}")
        
        cursor.close()
        conn.close()
        
        # Now create tables in the database
        conn = get_db_connection(database_name=Config.DB_NAME)
        conn.autocommit = True
        
        create_survey_tables(conn)
        
        conn.close()
        logger.info("Database initialized successfully")
        
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# Flask Routes
@app.route('/')
def index():
    """Home page"""
    with request_duration.labels(method='GET', endpoint='/').time():
        return render_template('index.html')

@app.route('/api/survey', methods=['POST'])
def conduct_survey_api():
    """API endpoint to submit a survey"""
    start_time = time.time()
    
    try:
        # Get JSON data from request
        data = request.get_json()
        if not data or 'answers' not in data:
            survey_failures.inc()
            return jsonify({'error': 'No JSON data provided or missing answers field'}), 400
        
        # Validate that answers is a list
        if not isinstance(data.get('answers'), list):
            survey_failures.inc()
            return jsonify({'error': 'Answers must be a list'}), 400
        
        # Validate each answer has required fields
        for answer in data['answers']:
            if not isinstance(answer, dict) or 'question_id' not in answer or 'answer_value' not in answer:
                survey_failures.inc()
                return jsonify({'error': 'Each answer must have question_id and answer_value'}), 400
        
        # Connect to database - let get_db_connection decide which DB to use
        conn = get_db_connection()
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

@app.route('/api/responses', methods=['GET'])
def get_responses():
    """API endpoint to get all survey responses"""
    with request_duration.labels(method='GET', endpoint='/api/responses').time():
        try:
            conn = get_db_connection()
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

@app.route('/api/questions', methods=['GET'])
def get_questions():
    """API endpoint to get survey questions"""
    with request_duration.labels(method='GET', endpoint='/api/questions').time():
        try:
            conn = get_db_connection()
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

@app.route('/health')
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        active_connections.inc()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        active_connections.dec()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({'status': 'unhealthy', 'database': 'disconnected', 'error': str(e)}), 500

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

if __name__ == "__main__":
    # Initialize database
    logger.info("Starting Patient Survey Application")
    initialize_database()
    
    # Run Flask app - make host configurable via environment variable
    host = os.environ.get('FLASK_HOST', '127.0.0.1')  # Default to localhost for security
    port = int(os.environ.get('FLASK_PORT', 8001))
    
    logger.info(f"Starting server on {host}:{port}")
    app.run(host=host, port=port, debug=False)
