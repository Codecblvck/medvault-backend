from app.auth import routes as auth_routes
from app.records.routes import records_bp
from app.audit import routes as audit_bp
from app.patients import routes as patient_routes
# from app.access_control.routes import access_control_bp


def register_blueprints(app):
    app.register_blueprint(auth_routes.bp, url_prefix="/auth")
    app.register_blueprint(records_bp, url_prefix="/records")
    app.register_blueprint(audit_bp.bp, url_prefix="/audit")
    app.register_blueprint(patient_routes.bp, url_prefix="/patients")
