from flask import jsonify
from app.extensions import jwt


@jwt.unauthorized_loader
def missing_token_callback(error_message):
    return jsonify({"error": "Missing or invalid authorization token."}), 401


@jwt.invalid_token_loader
def invalid_token_callback(error_message):
    return jsonify({"error": "The provided token is invalid."}), 401


@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Your session has expired. Please log in again."}), 401


@jwt.user_lookup_error_loader
def user_lookup_error_callback(_jwt_header, _jwt_data):
    return jsonify({"error": "Account is no longer active."}), 401
