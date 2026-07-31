"""Access control package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .models import AuditLog
from .logger import log_access
from .actions import AuditAction

__all__ = ["AuditLog", "log_access", "AuditAction"]
