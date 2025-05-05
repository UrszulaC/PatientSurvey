import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_CONFIG = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER'),
        'password': os.getenv('DB_PASSWORD'),
        'database': os.getenv('DB_NAME', 'patient_survey_db'),
        'raise_on_warnings': True
    }
    
    @classmethod
    def validate(cls):
        missing = [k for k, v in cls.DB_CONFIG.items() if v is None and k != 'password']
        if missing:
            raise ValueError(f"Missing required config values: {missing}")

Config.validate()