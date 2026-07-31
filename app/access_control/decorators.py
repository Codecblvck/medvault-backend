from functools import wraps
from flask import jsonify, request
from flask_jwt_extended import current_user

from app.access_control.permissions import has_permission, PermissionAction
from app.audit import log_access, AuditAction


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
                    details=f"Permission matrix rejected {action.value} on {func.__name__}.",
                )
                return (
                    jsonify({"error": "Access denied: insufficient role permissions."}),
                    403,
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator
