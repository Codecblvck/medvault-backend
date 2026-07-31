import os
from flask import Flask
from flask_migrate import migrate
from app.config import Config, TestingConfig, DevelopmentConfig
from app.extensions import db, jwt, migrate, bcrypt
from app.blueprint_registry import register_blueprints


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    env = os.environ.get("FLASK_ENV", "development")

    if env == "production":
        app.config.from_object(Config)
    elif env == "testing":
        app.config.from_object(TestingConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)

    from app.access_control import jwt_handlers  
    from app.model_registry import (
        auth_models,
        access_control_models,
        audit_models,
        records_models,
    )
    register_blueprints(app)

    return app
