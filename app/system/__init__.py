"""Access control package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .access import (
    Role,
    RoleName,
    PermissionAction,
    role_required,
    permission_required,
    has_permission,
    can_upload_record_type,
    can_view_record,
)

from .audit import AuditLog, log_access, AuditAction
from .crypto import encrypt_data, decrypt_data
from .storage import upload_file, get_file_url, delete_file, get_storage_provider, get_s3_client
from .validators import is_valid_email

__all__ = [
    "Role",
    "RoleName",
    "PermissionAction",
    "role_required",
    "has_permission",
    "can_upload_record_type",
    "permission_required",
    "can_view_record",
    "AuditLog",
    "log_access",
    "encrypt_data",
    "decrypt_data",
    "AuditAction"
]
