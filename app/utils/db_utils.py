import mysql.connector
from app.config import Config

def get_db_connection():
    """Get a new database connection with pooling"""
    return mysql.connector.connect(**Config.DB_CONFIG)

def with_db_connection(func):
    """Decorator that can work with or without explicit connection"""
    def wrapper(conn=None, *args, **kwargs):
        should_close = False
        try:
            if conn is None:
                conn = get_db_connection()
                should_close = True
            return func(conn, *args, **kwargs)
        finally:
            if should_close and conn and conn.is_connected():
                conn.close()
    
    # Copy original function attributes for testing
    wrapper.original_func = func
    return wrapper