from enum import Enum
from app.access_control import RoleName
from app.records.models import RecordType


class PermissionAction(Enum):
    manage_users = "manage_users"
    upload_records = "upload_records"
    view_records = "view_records"
    edit_own_records = "edit_own_records"
    view_logs = "view_logs"
    link_patient_identity = "link_patient_identity"


ROLE_PERMISSIONS = {
    RoleName.admin: [PermissionAction.manage_users],
    RoleName.doctor: [PermissionAction.upload_records, PermissionAction.view_records, PermissionAction.edit_own_records],
    RoleName.nurse: [PermissionAction.upload_records, PermissionAction.view_records],
    RoleName.lab_technician: [PermissionAction.upload_records, PermissionAction.view_records],
    RoleName.records_officer: [PermissionAction.view_records],
    RoleName.patient: [PermissionAction.view_records],
    RoleName.auditor: [PermissionAction.view_logs],
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
