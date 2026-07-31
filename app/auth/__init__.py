"""Authentication package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .models import User
from .security import reset_failed_attempts, register_failed_attempt, is_account_locked
from .email_utils import is_valid_email

__all__ = [
    "User",
    "reset_failed_attempts",
    "register_failed_attempt",
    "is_account_locked",
    "is_valid_email",
]
