from flask import Flask

def create_app():
    app = Flask(__name__)
    app.config.from_object('app.config.Config')
    
    # Import and register routes directly from main.py
    from app.main import app as main_app
    
    # Copy all the routes and view functions from main.py
    for rule in main_app.url_map.iter_rules():
        if rule.endpoint != 'static':  # Skip static files
            view_func = main_app.view_functions[rule.endpoint]
            app.add_url_rule(rule.rule, endpoint=rule.endpoint, view_func=view_func, methods=rule.methods)
    
    return app

