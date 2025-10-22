import os
from flask import Flask, jsonify
from application import config
from application.database import db
from application.config import LocalDevelopmentConfig

# Note: Beatification and dark mode is left for future improvements

app = None

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # Load configuration based on environment
    env = os.getenv('FLASK_ENV', 'development')
    if env == 'production':
        # app.config.from_object(config.ProductionConfig)
        raise NotImplementedError("Production configuration is not implemented yet.")
    elif env == 'testing':
        # app.config.from_object(config.TestingConfig)
        raise NotImplementedError("Testing configuration is not implemented yet.")
    else:
        app.config.from_object(LocalDevelopmentConfig)

    # Initialize database with app
    db.init_app(app)
    app.app_context().push()

    return app

app = create_app()

# import controllers after app creation to avoid circular imports
from application.controllers import *

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)