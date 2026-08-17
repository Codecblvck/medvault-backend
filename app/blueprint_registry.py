from app.auth import routes as auth_routes
from app.records import routes as records_bp
from app.audit import routes as audit_bp
from app.patients import routes as patient_routes
from app.system import routes as system_bp


def register_blueprints(app):
    app.register_blueprint(auth_routes.bp, url_prefix="/auth")
    app.register_blueprint(records_bp.bp, url_prefix="/records")
    app.register_blueprint(audit_bp.bp, url_prefix="/audit")
    app.register_blueprint(patient_routes.bp, url_prefix="/patients")
    app.register_blueprint(system_bp.bp, url_prefix="/system")
