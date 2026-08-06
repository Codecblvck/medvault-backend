"""Authentication package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .models import User
from .security import reset_failed_attempts, register_failed_attempt, is_account_locked

__all__ = [
    "User",
    "reset_failed_attempts",
    "register_failed_attempt",
    "is_account_locked",
]
