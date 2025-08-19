import pyodbc
from app.config import Config
import logging

logger = logging.getLogger(__name__)

def get_db_connection():
    """
    Establishes a pyodbc connection to the configured SQL Server database.
    Only connects to the application database defined in Config.DB_NAME.
    """
    try:
        # Always connect directly to the app database
        conn_string = Config.DB_CONNECTION_STRING + f"DATABASE={Config.DB_NAME};"

        # pyodbc connections default to autocommit=False.
        # We will manage commits explicitly in the decorated functions.
        connection = pyodbc.connect(conn_string)
        logger.info(f"Connected to database {Config.DB_NAME}")
        return connection
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        logger.error(f"Database connection error: {sqlstate} - {ex}")
        # Don’t raise here — allow app to keep running (metrics stay available)
        return None

def with_db_connection(func):
    """
    Decorator to manage database connections for functions.
    It passes a database connection object to the decorated function.
    Handles connection opening, closing, and error rollback/commit.
    If the database is unavailable, the function will receive None and can handle it gracefully.
    """
    def wrapper(*args, **kwargs):
        conn = None
        try:
            conn = get_db_connection()
            if conn is None:
                logger.warning("Database unavailable — skipping DB operation.")
                return None

            result = func(conn, *args, **kwargs)
            conn.commit()  # Commit changes if no exception
            return result
        except Exception as e:
            if conn:
                conn.rollback()  # Rollback on exception
            logger.error(f"Database operation failed: {e}")
            raise  # Re-raise the exception after rollback
        finally:
            if conn:
                conn.close()  # Ensure connection is closed
    return wrapper

