from flask_jwt_extended import jwt_required
from sqlalchemy import text

from app.extensions import db
from app import system as core
from app.config import Config
from flask import Blueprint, jsonify


bp = Blueprint("system", __name__)




@bp.route("/health", methods=["GET"])
@jwt_required()
def system_health():
    """
    Check the health of the API's critical dependencies:
    - API: route is responding
    - Database: simple database query
    - Storage: configured S3-compatible object storage
    """

    database_status = "healthy"
    storage_status = "healthy"

    # Database health
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        database_status = "unhealthy"

    # Storage health
    try:
        client = core.get_s3_client()

        client.head_bucket(Bucket=Config.S3_BUCKET_NAME)

    except Exception:
        storage_status = "unhealthy"

    overall_status = (
        "healthy"
        if database_status == "healthy" and storage_status == "healthy"
        else "degraded"
    )

    return (
        jsonify(
            {
                "status": overall_status,
                "api": {"status": "healthy"},
                "database": {"status": database_status},
                "storage": {
                    "status": storage_status,
                    "provider": core.get_storage_provider(),
                },
            }
        ),
        200,
    )



