"""Record package for the hospital records system.

Re-export common symbols so callers can import from
`app.access_control` instead of deeper modules.
"""

from .models import Record, RecordType, Patient

__all__ = ["Record", "RecordType", "Patient"]
