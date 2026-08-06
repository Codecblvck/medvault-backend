import sqlalchemy as sa

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, current_user


from app import system as core
from app.audit import AuditLog
from app.extensions import db
from app.records import Record



bp = Blueprint("audit", __name__)


@bp.route("/logs", methods=["GET"])
@jwt_required()
@core.role_required([core.RoleName.admin, core.RoleName.auditor])
def view_logs():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    offset = (page - 1) * limit

    stmt = sa.select(AuditLog)
    count_stmt = sa.select(sa.func.count()).select_from(AuditLog)

    user_id_param = request.args.get("user_id")
    if user_id_param:
        stmt = stmt.where(AuditLog.user_id == user_id_param)
        count_stmt = count_stmt.where(AuditLog.user_id == user_id_param)

    action_param = request.args.get("action")
    if action_param:
        stmt = stmt.where(AuditLog.action == action_param)
        count_stmt = count_stmt.where(AuditLog.action == action_param)

    status_param = request.args.get("status")
    if status_param:
        stmt = stmt.where(AuditLog.status == status_param)
        count_stmt = count_stmt.where(AuditLog.status == status_param)

    date_from = request.args.get("date_from")
    if date_from:
        stmt = stmt.where(AuditLog.timestamp >= date_from)
        count_stmt = count_stmt.where(AuditLog.timestamp >= date_from)

    date_to = request.args.get("date_to")
    if date_to:
        stmt = stmt.where(AuditLog.timestamp <= date_to)
        count_stmt = count_stmt.where(AuditLog.timestamp <= date_to)

    total = db.session.scalar(count_stmt) or 0

    stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
    logs = db.session.execute(stmt).scalars().all()

    has_more = (offset + len(logs)) < total

    core.log_access(
        action=core.AuditAction.audit_logs_viewed.value,
        status="Success",
        request=request,
        user=current_user,
        details=f"Viewed audit log listing, page {page}, limit {limit}.",
    )

    return (
        jsonify(
            {
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": has_more,
                "logs": [
                    {
                        "id": l.id,
                        "user_name": (
                            l.user.full_name if l.user else "Unknown or unauthenticated"
                        ),
                        "role_at_time": l.role_at_time,
                        "action": l.action,
                        "record_id": str(l.record_id) if l.record_id else None,
                        "ip_address": l.ip_address,
                        "status": l.status,
                        "timestamp": l.timestamp.isoformat() + "Z",
                    }
                    for l in logs
                ],
            }
        ),
        200,
    )


@bp.route("/report/<uuid:record_id>", methods=["GET"])
@jwt_required()
@core.role_required([core.RoleName.admin, core.RoleName.auditor])
def view_report(record_id):
    record = Record.query.get(record_id)
    if not record:
        core.log_access(
            action=core.AuditAction.audit_report_viewed.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Requested access report for nonexistent record {record_id}.",
        )
        return jsonify({"error": "No record found."}), 404

    stmt = sa.select(AuditLog).where(AuditLog.record_id == record_id)
    logs = db.session.scalars(stmt).all()

    total_accesses = len(logs)

    access_history = [
        {
            "user_name": (
                log.user.full_name if log.user else "Unknown or unauthenticated"
            ),
            "action": log.action,
            "status": log.status,
            "timestamp": log.timestamp.isoformat() + "Z",
        }
        for log in logs
    ]

    core.log_access(
        action=core.AuditAction.audit_report_viewed.value,
        status="Success",
        request=request,
        user=current_user,
        record_id=record.id,
        details=f"Generated access report for record {record_id}, {total_accesses} entries.",
    )

    return (
        jsonify(
            {
                "record_id": str(record_id),
                "total_accesses": total_accesses,
                "access_history": access_history,
            }
        ),
        200,
    )
