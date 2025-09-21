import os
import logging
import json
import time
import pyodbc
from flask import Flask, request, jsonify, render_template, make_response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST, Gauge, Histogram
from app.utils.db_utils import get_db_connection
from app.config import Config

# --------------------------
# Logging
# --------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --------------------------
# Flask app and templates
# --------------------------
app = Flask(__name__)
base_dir = os.path.dirname(os.path.abspath(__file__))

possible_paths = [
    os.path.join(base_dir, 'templates'),
    os.path.join(base_dir, '..', 'templates'),
    os.path.join(base_dir, 'app', 'templates'),
    'templates'
]

for path in possible_paths:
    absolute_path = os.path.abspath(path)
    if os.path.exists(absolute_path) and os.path.isdir(absolute_path):
        app.template_folder = absolute_path
        logger.info(f"Using template folder: {absolute_path}")
        break
else:
    app.template_folder = 'templates'
    logger.warning("No template folder found, using default")

# --------------------------
# Prometheus metric helpers
# --------------------------
def get_or_create_counter(name, description, registry=None):
    try:
        return Counter(name, description, registry=registry)
    except ValueError:
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

def get_or_create_histogram(name, description, labelnames=(), registry=None):
    try:
        return Histogram(name, description, labelnames=labelnames, registry=registry)
    except ValueError:
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

def get_or_create_gauge(name, description, registry=None):
    try:
        return Gauge(name, description, registry=registry)
    except ValueError:
        from prometheus_client import REGISTRY
        return REGISTRY._names_to_collectors[name]

# --------------------------
# Prometheus metrics
# --------------------------
survey_counter = get_or_create_counter('patient_survey_submissions_total', 'Total number of patient surveys submitted')
survey_duration = get_or_create_counter('patient_survey_duration_seconds_total', 'Total time spent completing surveys')
survey_failures = get_or_create_counter('patient_survey_failures_total', 'Total failed survey submissions')
active_surveys = get_or_create_counter('active_surveys_total', 'Number of active surveys initialized')
question_count = get_or_create_counter('survey_questions_total', 'Total number of questions initialized')

request_duration = get_or_create_histogram('http_request_duration_seconds', 'HTTP request duration in seconds', ['method', 'endpoint'])
active_connections = get_or_create_gauge('db_active_connections', 'Number of active database connections')

# --------------------------
# Initialize DB and tables
# --------------------------
def create_survey_tables(conn):
    try:
        cursor = conn.cursor()

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

        cursor.execute("""
            IF OBJECT_ID('responses', 'U') IS NULL
            CREATE TABLE responses (
                response_id INT IDENTITY(1,1) PRIMARY KEY,
                survey_id INT NOT NULL,
                submitted_at DATETIME DEFAULT GETDATE(),
                FOREIGN KEY (survey_id) REFERENCES surveys(survey_id) ON DELETE CASCADE
            )
        """)

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

        # Insert default survey if not exists
        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            cursor.execute("""
                INSERT INTO surveys (title, description, is_active)
                VALUES (?, ?, ?)
            """, ('Patient Experience Survey', 'Survey to collect feedback', True))
            conn.commit()
            cursor.execute("SELECT SCOPE_IDENTITY()")
            survey_id = int(cursor.fetchone()[0])
            active_surveys.inc()
        else:
            survey_id = survey[0]

        # Insert default questions if not exist
        cursor.execute("SELECT COUNT(*) FROM questions WHERE survey_id = ?", (survey_id,))
        if cursor.fetchone()[0] == 0:
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
                """, (survey_id, q['text'], q['type'], q['required'], json.dumps(q.get('options')) if 'options' in q else None))
                question_count.inc()

        conn.commit()

    except Exception as e:
        survey_failures.inc()
        conn.rollback()
        logger.error(f"Database initialization failed: {e}")
        raise

def initialize_database():
    try:
        conn = get_db_connection(database_name=None)
        conn.autocommit = True
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sys.databases WHERE name = ?", (Config.DB_NAME,))
        if not cursor.fetchone():
            cursor.execute(f"CREATE DATABASE [{Config.DB_NAME}]")
            logger.info(f"Created database {Config.DB_NAME}")
        cursor.close()
        conn.close()

        conn = get_db_connection(database_name=Config.DB_NAME)
        conn.autocommit = True
        create_survey_tables(conn)
        conn.close()
        logger.info("Database initialized successfully")

    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

# --------------------------
# Sync metrics from DB
# --------------------------
def sync_metrics_with_db():
    try:
        conn = get_db_connection(database_name=Config.DB_NAME)
        cursor = conn.cursor()

        # Submissions
        cursor.execute("SELECT COUNT(*) FROM responses")
        total_responses = cursor.fetchone()[0] or 0
        survey_counter._value.set(total_responses)

        # Active surveys
        cursor.execute("SELECT COUNT(*) FROM surveys WHERE is_active = 1")
        active_surveys._value.set(cursor.fetchone()[0] or 0)

        # Questions
        cursor.execute("SELECT COUNT(*) FROM questions")
        question_count._value.set(cursor.fetchone()[0] or 0)

        # Failures - runtime only (or implement DB table)
        survey_failures._value.set(0)

        # Duration - runtime only unless stored
        survey_duration._value.set(0)

        # DB connections snapshot
        cursor.execute("""
            SELECT COUNT(*) FROM sys.dm_exec_sessions WHERE database_id = DB_ID(?)
        """, (Config.DB_NAME,))
        active_connections._value.set(cursor.fetchone()[0] or 0)

        conn.close()
        logger.info(f"Metrics synced from DB: {total_responses} submissions, "
                    f"{active_surveys._value.get()} active surveys, "
                    f"{question_count._value.get()} questions")
    except Exception as e:
        logger.error(f"Failed to sync metrics with DB: {e}")

# --------------------------
# Flask routes (API, metrics, health)
# --------------------------
@app.route('/')
def index():
    response = make_response(render_template('index.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/questions', methods=['GET'])
def get_questions():
    try:
        conn = get_db_connection(database_name=Config.DB_NAME)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT question_id, question_text, question_type, is_required, options
            FROM questions
        """)
        rows = cursor.fetchall()
        conn.close()

        questions = []
        for row in rows:
            questions.append({
                'question_id': row[0],
                'question_text': row[1],
                'question_type': row[2],
                'is_required': bool(row[3]),
                'options': json.loads(row[4]) if row[4] else None
            })

        return jsonify(questions), 200
    except Exception as e:
        logger.error(f"Failed to fetch questions: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/survey', methods=['POST'])
def conduct_survey_api():
    start_time = time.time()
    try:
        data = request.get_json()
        if not data or 'answers' not in data:
            survey_failures.inc()
            return jsonify({'error': 'Missing answers'}), 400
        if not isinstance(data['answers'], list):
            survey_failures.inc()
            return jsonify({'error': 'Answers must be a list'}), 400

        for ans in data['answers']:
            if 'question_id' not in ans or 'answer_value' not in ans:
                survey_failures.inc()
                return jsonify({'error': 'Invalid answer format'}), 400

        conn = get_db_connection()
        active_connections.inc()
        cursor = conn.cursor()

        cursor.execute("SELECT survey_id FROM surveys WHERE title = 'Patient Experience Survey'")
        survey = cursor.fetchone()
        if not survey:
            conn.close()
            active_connections.dec()
            survey_failures.inc()
            return jsonify({'error': 'Survey not found'}), 404
        survey_id = survey[0]

        cursor.execute("INSERT INTO responses (survey_id) VALUES (?)", (survey_id,))
        conn.commit()
        cursor.execute("SELECT SCOPE_IDENTITY()")
        response_id = int(cursor.fetchone()[0])

        for ans in data['answers']:
            cursor.execute("INSERT INTO answers (response_id, question_id, answer_value) VALUES (?, ?, ?)",
                           (response_id, ans['question_id'], ans['answer_value']))
        conn.commit()
        conn.close()
        active_connections.dec()

        # Update metrics
        survey_counter.inc()
        survey_duration.inc(time.time() - start_time)

        logger.info(f"Survey recorded ID: {response_id}")
        return jsonify({'message': 'Survey submitted', 'response_id': response_id}), 201
    except Exception as e:
        survey_failures.inc()
        if 'conn' in locals():
            conn.close()
            active_connections.dec()
        logger.error(f"Survey submission failed: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/metrics')
def metrics():
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/health')
def health_check():
    try:
        conn = get_db_connection()
        active_connections.inc()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
        active_connections.dec()
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'error': str(e)}), 500

# --------------------------
# Main
# --------------------------
if __name__ == "__main__":
    logger.info("Starting Patient Survey App")

    # Initialize DB and tables
    initialize_database()

    # Ensure metric objects exist (no-op increments)
    survey_counter.inc(0)
    survey_duration.inc(0)
    survey_failures.inc(0)
    active_surveys.inc(0)
    question_count.inc(0)
    request_duration.observe(0)
    active_connections.set(0)

    # Sync metrics with actual DB values
    with app.app_context():
        sync_metrics_with_db()

    host = os.environ.get('FLASK_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_PORT', 8001))
    logger.info(f"Server starting on {host}:{port}")
    app.run(host=host, port=port, debug=False)






