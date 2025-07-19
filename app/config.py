import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER')
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    DB_NAME = os.getenv('DB_NAME', 'patient_survey_db') # Default for main app
    DB_TEST_NAME = 'patient_survey_test' # Explicitly define test database name

    # ODBC Driver Name - this needs to be installed on the Jenkins agent
    # Common for Linux: 'ODBC Driver 17 for SQL Server'
    # Common for Windows: 'ODBC Driver 17 for SQL Server' or '{SQL Server}'
    ODBC_DRIVER = '{ODBC Driver 17 for SQL Server}'

    # Connection string for pyodbc
    # Note: DB_NAME is for the main application.
    # For tests, we'll build a string that connects without a specific DB first.
    DB_CONNECTION_STRING = (
        f"DRIVER={ODBC_DRIVER};"
        f"SERVER={DB_HOST},1433;" # Azure SQL default port is 1433, specify it here
        f"UID={DB_USER};"
        f"PWD={DB_PASSWORD};"
        f"Encrypt=yes;" # Recommended for Azure SQL
        f"TrustServerCertificate=no;" # Recommended for Azure SQL
        f"Connection Timeout=30;" # Increase timeout if needed
    )

    @classmethod
    def validate(cls):
        missing = []
        if not cls.DB_HOST:
            missing.append('DB_HOST')
        if not cls.DB_USER:
            missing.append('DB_USER')
        if not cls.DB_PASSWORD:
            # For security, you might not want to check if password is None here directly.
            # But the connection will fail if it's truly missing.
            pass
        if not cls.ODBC_DRIVER:
            missing.append('ODBC_DRIVER')

        if missing:
            raise ValueError(f"Missing required config values: {missing}")

# Validate configuration on import
Config.validate()
