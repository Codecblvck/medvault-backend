from enum import Enum


class AuditAction(Enum):
    # Authentication
    login_success = "Login Success"
    login_failed = "Login Failed"
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
    duplicate_patient_warning = "Duplicate Patient Warning"

    # Audit
    audit_logs_viewed = "Audit Logs Viewed"
    audit_report_viewed = "Audit Report Viewed"
