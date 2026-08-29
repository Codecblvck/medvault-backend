import os
from flask import Flask, jsonify
from flask_migrate import migrate
from app.config import Config, TestingConfig, DevelopmentConfig
from app.extensions import db, jwt, migrate, bcrypt, cors, ma, limiter
from app.blueprint_registry import register_blueprints


def create_app():
    app = Flask(__name__)
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
    ma.init_app(app)
    limiter.init_app(app)
    cors.init_app(
        app,
        resources={
            "/*": {"origins": ["https://medvault-two.vercel.app", "http://localhost:5173"]}
        },
    )

    from app.model_registry import (
        auth_models,
        audit_models,
        records_models,
    )

    register_blueprints(app)
    @app.errorhandler(429)
    def ratelimit_handler(e):
        return jsonify({"error": "Too many requests. Please try again shortly."}), 429

    return app
