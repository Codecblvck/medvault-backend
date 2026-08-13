import hashlib
import json
import uuid
import enum

from sqlalchemy import select
from app.extensions import db
from app.audit import AuditLog


# ===== AUDIT ACTIONS =====
class AuditAction(enum.Enum):
    # Authentication
    login_success = "Login Success"
    login_failed = "Login Failed"
    logout_success = "Logout Success"
    account_locked = "Account Locked"
    account_unlocked = "Account Unlocked"

    # Records
    record_viewed = "Record Viewed"
    record_uploaded = "Record Uploaded"

    # Access control
    permission_denied = "Permission Denied"

    # Admin / user management
    user_created = "User Created"
    user_updated = "User Updated"
    role_changed = "Role Changed"

    # Patients
    patient_created = "Patient Created"
    patient_viewed = "Patient Viewed"
    patient_updated = "Patient Updated"
    duplicate_patient_warning = "Duplicate Patient Warning"
    patient_list_viewed = "Patient List Viewed"

    # Audit
    audit_logs_viewed = "Audit Logs Viewed"
    audit_report_viewed = "Audit Report Viewed"


def log_access(
    action,
    status,
    request,
    user=None,
    attempted_email=None,
    record_id=None,
    details=None,
):
    """
    Records one audit log entry, chained onto the previous entry's hash.

    Either user (a real User object) or attempted_email (a plain string)
    should be provided, not both. user=None is the case for a login
    attempt against an email matching no real account, there is no user
    row to attach the log to, so the attempted email is stored directly
    instead.

    details is an optional short human readable string describing what
    changed, for example "role changed to doctor", used on routes where
    the action label alone does not say enough for an audit review.
    """
    if hasattr(action, "value"):
        action = action.value

    if record_id is not None:
        try:
            record_id = uuid.UUID(str(record_id))
        except ValueError:
            raise ValueError("Invalid record_id provided to log_access.")

    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc())
    recent_log = db.session.scalar(stmt)

    audit = AuditLog()

    if not recent_log:
        audit.previous_hash = "GENESIS"
    else:
        audit.previous_hash = recent_log.entry_hash

    if user is not None:
        audit.user_id = user.id
        audit.role_at_time = user.role.role_name.value
        audit.attempted_email = None
    else:
        audit.user_id = None
        audit.role_at_time = None
        audit.attempted_email = attempted_email

    audit.action = action
    audit.record_id = record_id
    audit.details = details
    audit.ip_address = request.remote_addr
    audit.status = status

    combined_dict = {
        "user_id": audit.user_id,
        "attempted_email": audit.attempted_email,
        "action": audit.action,
        "details": audit.details,
        "status": audit.status,
        "record_id": str(audit.record_id),
        "previous_hash": audit.previous_hash,
    }
    combined_bytes = json.dumps(combined_dict, sort_keys=True).encode("utf-8")
    audit.entry_hash = hashlib.sha256(combined_bytes).hexdigest()

    db.session.add(audit)
    db.session.commit()

    return audit
