# Database configuration
import os
from dotenv import load_dotenv

load_dotenv()  # Load from .env file

HOST = os.getenv('HOST', 'localhost')
USER = os.getenv('USER')
PASSWORD = os.getenv('PASSWORD')
DATABASE = os.getenv('DATABASE', 'patient_survey_db')