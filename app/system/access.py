import enum
from typing import TYPE_CHECKING
from functools import wraps

from flask import jsonify, request
from flask_jwt_extended import current_user
from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db
from app.records import RecordType
from .audit import AuditAction, log_access

if TYPE_CHECKING:
    from app.auth.models import User


class RoleName(enum.Enum):
    admin = "admin"
    doctor = "doctor"
    nurse = "nurse"
    lab_technician = "lab_technician"
    records_officer = "records_officer"
    auditor = "auditor"
    patient = "patient"

class PermissionAction(enum.Enum):
    manage_users = "manage_users"
    upload_records = "upload_records"
    view_records = "view_records"
    view_record_detail = "view_record_detail"
    view_logs = "view_logs"
    edit_own_records = "edit_own_records"
    link_patient_identity = "link_patient_identity"
    register_patient = "register_patient"
    view_patients = "view_patients"
    edit_patients = "edit_patients"
    assign_doctor = "assign_doctor"

class Role(db.Model):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, values_callable=lambda x: [i.value for i in x]),
        unique=True,
        nullable=False,
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="role")


def role_required(allowed_roles):
    """
    Restricts a route to a fixed whitelist of roles, for example admin only.
    Only logs the denial case. A route that passes this check is expected
    to log its own success or business outcome, since only the route body
    knows what actually happened.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            user_role_name = current_user.role.role_name if current_user else None
            is_allowed = bool(current_user) and user_role_name in allowed_roles

            if not is_allowed:
                log_access(
                    action=AuditAction.permission_denied,
                    status="Failed",
                    request=request,
                    user=current_user,
                    details=f"Role whitelist rejected access to {func.__name__}.",
                )
                return (
                    jsonify({"error": "Access denied: insufficient role permissions."}),
                    403,
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


def permission_required(action: PermissionAction):
    """
    Restricts a route based on the role permission matrix, for example
    PermissionAction.upload_records. Only logs the denial case, for the
    same reason as role_required above.
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            is_allowed = bool(current_user) and has_permission(
                current_user.role.role_name, action
            )

            if not is_allowed:
                log_access(
                    action=AuditAction.permission_denied,
                    status="Failed",
                    request=request,
                    user=current_user,
                    details=f"Permission matrix rejected {action} on {func.__name__}.",
                )
                return (
                    jsonify({"error": "Access denied: insufficient role permissions."}),
                    403,
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator


# ===== PERMISSION ALLOWLIST =====
ROLE_PERMISSIONS = {
    RoleName.admin: [
        PermissionAction.manage_users,
        PermissionAction.view_records,
        PermissionAction.view_logs,
        PermissionAction.link_patient_identity,
        PermissionAction.view_patients,
        PermissionAction.edit_patients,
        PermissionAction.assign_doctor,
    ],
    RoleName.doctor: [
        PermissionAction.upload_records,
        PermissionAction.view_records,
        PermissionAction.view_record_detail,
        PermissionAction.edit_own_records,
        PermissionAction.view_patients,
        PermissionAction.edit_patients,
    ],
    RoleName.nurse: [
        PermissionAction.upload_records,
        PermissionAction.view_records,
        PermissionAction.view_record_detail,
        PermissionAction.register_patient,
        PermissionAction.view_patients,
        PermissionAction.edit_patients,
    ],
    RoleName.lab_technician: [
        PermissionAction.upload_records,
        PermissionAction.view_records,
        PermissionAction.view_record_detail,
        PermissionAction.view_patients,
    ],
    RoleName.records_officer: [
        PermissionAction.view_records,
        PermissionAction.view_record_detail,
        PermissionAction.register_patient,
        PermissionAction.link_patient_identity,
        PermissionAction.view_patients,
        PermissionAction.edit_patients,
        PermissionAction.assign_doctor,
    ],
    RoleName.patient: [
        PermissionAction.view_records,
        PermissionAction.view_record_detail,
    ],
    RoleName.auditor: [
        PermissionAction.view_logs,
    ],
}

UPLOAD_TYPE_PERMISSIONS = {
    RoleName.doctor: [
        RecordType.lab_report,
        RecordType.imaging,
        RecordType.prescription,
        RecordType.discharge_summary,
    ],
    RoleName.nurse: [RecordType.vitals, RecordType.clinical_notes],
    RoleName.lab_technician: [RecordType.lab_report],
    RoleName.records_officer: [],
}


def has_permission(role_name, action):
    return action in ROLE_PERMISSIONS.get(role_name, [])


def can_upload_record_type(role_name, record_type):
    return record_type in UPLOAD_TYPE_PERMISSIONS.get(role_name, [])


def can_view_record(user, record):
    """
    Returns True if the given user is permitted to view the given record.

    Staff roles are already gated by the permission_required decorator
    at the route level (view_records action) before this is ever called,
    so this function's only job is the patient-specific ownership check:
    a patient may only view a record linked to their own patient_id.
    """
    if user.role.role_name != RoleName.patient:
        return True
    return user.patient_id is not None and record.patient_id == user.patient_id
