"""Access control package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .models import Role, RoleName
from .permissions import has_permission, PermissionAction, can_upload_record_type
from .decorators import role_required, permission_required

__all__ = [
    "Role",
    "RoleName",
    "has_permission",
    "role_required",
    "PermissionAction",
    "can_upload_record_type",
    "permission_required"
]
