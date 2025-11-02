import os
from flask import Flask, jsonify
from application import config
from application.database import db
from application.config import LocalDevelopmentConfig
from flask_restful import Api

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

# Register RESTful API and resources
api = Api(app)
try:
    # Import resources lazily so they can access models and db
    from application.api_appointments import AppointmentListResource, AppointmentResource
    api.add_resource(AppointmentListResource, '/api/appointments')
    api.add_resource(AppointmentResource, '/api/appointments/<int:appt_id>')
    try:
        from application.api_appointments import PublicDoctorAvailabilityResource
        api.add_resource(PublicDoctorAvailabilityResource, '/api/public/doctor/<int:doctor_id>/availability')
    except Exception:
        pass
except Exception:
    # If import fails during indexing/static analysis it's non-fatal here
    pass

# import controllers after app creation to avoid circular imports
from application.controllers import *

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)