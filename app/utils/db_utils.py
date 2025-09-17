import pyodbc
from app.config import Config
import logging

logger = logging.getLogger(__name__)

def get_db_connection(database_name=None):
    """
    Establishes a pyodbc connection to the SQL Server.
    If database_name is provided, connects directly to that database.
    Otherwise, connects without specifying a database (e.g., to master)
    which is useful for DDL operations like CREATE/DROP DATABASE.
    """
    try:
        # Check if we're in testing mode and use test database if no specific database is provided
        if database_name is None:
            try:
                from flask import current_app
                if current_app and current_app.config.get('TESTING'):
                    database_name = Config.DB_TEST_NAME
                else:
                    database_name = Config.DB_NAME
            except RuntimeError:
                # No app context, use production database
                database_name = Config.DB_NAME
        
        conn_string = Config.DB_CONNECTION_STRING
        if database_name:
            conn_string += f"DATABASE={database_name};"

        # pyodbc connections default to autocommit=False.
        # We will manage commits explicitly in the decorated functions.
        connection = pyodbc.connect(conn_string)
        return connection
    except pyodbc.Error as ex:
        sqlstate = ex.args[0]
        logger.error(f"Database connection error: {sqlstate} - {ex}")
        raise

def with_db_connection(func):
    """
    Decorator to manage database connections for functions.
    It passes a database connection object to the decorated function.
    Handles connection opening, closing, and error rollback/commit.
    """
    def wrapper(*args, **kwargs):
        conn = None
        try:
            # If the function needs to connect to the test database for DDL,
            # it should pass database_name=Config.DB_TEST_NAME or None for master
            # The create_survey_tables function will handle database switching.
            # For other functions, we typically connect to the main app database.
            db_name_for_func = kwargs.pop('db_name', Config.DB_NAME)
            conn = get_db_connection(database_name=db_name_for_func)

            # Set row_factory for dictionary-like access if needed
            # For pyodbc, you can't set row_factory on the connection, but on the cursor
            # The decorated function will create its own cursor.

            result = func(conn, *args, **kwargs)
            conn.commit() # Commit changes if no exception
            return result
        except Exception as e:
            if conn:
                conn.rollback() # Rollback on exception
            logger.error(f"Database operation failed: {e}")
            raise # Re-raise the exception after rollback
        finally:
            if conn:
                conn.close() # Ensure connection is closed
    return wrapper
