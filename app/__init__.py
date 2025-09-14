from flask import Flask
from app.routes import main_bp

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')
    
    # Register blueprints
    app.register_blueprint(main_bp)
    
    return app
