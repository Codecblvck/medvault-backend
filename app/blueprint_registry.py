from app.auth.routes import auth_bp
from app.records.routes import records_bp
from app.audit.routes import audit_bp
# from app.access_control.routes import access_control_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(records_bp, url_prefix="/records")
    app.register_blueprint(audit_bp, url_prefix="/audit")
    # app.register_blueprint(access_control_bp, url_prefix="/access-control")
