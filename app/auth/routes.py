from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, current_user
import sqlalchemy as sa
from app.access_control import role_required, Role, RoleName
from app.extensions import bcrypt, db
from app.auth import (
    User,
    is_account_locked,
    register_failed_attempt,
    reset_failed_attempts,
    is_valid_email
)
from app.audit import AuditAction, log_access

auth_bp = Blueprint("auth", __name__)


# auth/routes.py
@auth_bp.route("/login", methods=["POST"])
def login():
    user_payload = request.get_json()
 
    if not user_payload:
        return (
            jsonify(
                {
                    "error": "Missing payload: Ensure you provide both email and password."
                }
            ),
            400,
        )
 
    columns_required = "email" not in user_payload or "password" not in user_payload
    if columns_required:
        return (
            jsonify(
                {
                    "error": "Missing payload: Ensure you provide both email and password."
                }
            ),
            400,
        )
 
    submitted_email = user_payload["email"]
 
    valid, result = is_valid_email(submitted_email)
    if not valid:
        return jsonify({"error": "Invalid email format."}), 400
 
    normalized_email = result
 
    stmt = sa.select(User).filter_by(email=normalized_email)
    user = db.session.scalar(stmt)
 
    if not user:
        log_access(
            action=AuditAction.login_failed.value,
            status="Blocked",
            request=request,
            attempted_email=normalized_email,
        )
        return jsonify({"error": "Invalid email or password."}), 401
 
    if is_account_locked(user):
        log_access(
            action=AuditAction.account_locked.value,
            status="Blocked",
            request=request,
            user=user,
        )
        return (
            jsonify(
                {"error": "Account is locked due to multiple failed login attempts."}
            ),
            423,
        )
 
    user_pswd = user_payload["password"]
    validate_pswd = bcrypt.check_password_hash(user.password_hash, user_pswd)
 
    if not validate_pswd:
        register_failed_attempt(user)
        log_access(
            action=AuditAction.login_failed.value,
            status="Blocked",
            request=request,
            user=user,
        )
        return jsonify({"error": "Invalid email or password."}), 401
 
    if not user.is_active:
        log_access(
            action=AuditAction.login_failed.value,
            status="Blocked",
            request=request,
            user=user,
        )
        return jsonify({"error": "Invalid email or password."}), 401
 
    reset_failed_attempts(user)
    access_token = create_access_token(identity=user.email)
 
    role = db.session.get(Role, user.role_id)
    role_name = role.role_name.value if role is not None else None
 
    log_access(
        action=AuditAction.login_success.value,
        status="Success",
        request=request,
        user=user,
    )
 
    return jsonify(
        {
            "token": access_token,
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "role": role_name,
            },
        }
    )

@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def get_own_profile():
    return (
        jsonify(
            {
                "id": current_user.id,
                "first_name": current_user.first_name,
                "last_name": current_user.last_name,
                "email": current_user.email,
                "role": current_user.role.role_name.value,
                "phone": current_user.phone,
                "department": current_user.department,
                "license_number": current_user.license_number,
            }
        ),
        200,
    )


@auth_bp.route("/me", methods=["PATCH"])
@jwt_required()
def update_own_profile():
    data = request.get_json() or {}

    if "phone" not in data and "department" not in data:
        return (
            jsonify(
                {"error": "Provide at least one field to update, phone or department."}
            ),
            400,
        )

    if "phone" in data:
        current_user.phone = data["phone"]
    if "department" in data:
        current_user.department = data["department"]

    db.session.commit()

    return (
        jsonify(
            {
                "id": current_user.id,
                "phone": current_user.phone,
                "department": current_user.department,
                "message": "Profile updated",
            }
        ),
        200,
    )


# ADMIN USER MANAGEMENT ROUTES
@auth_bp.route("/users/<int:user_id>", methods=["PATCH"])
@jwt_required()
@role_required([RoleName.admin])
def update_staff_user(user_id):
    payload = request.get_json() or {}

    if not payload:
        return jsonify({"error": "No fields provided to update."}), 400

    stmt = sa.select(User).filter_by(id=user_id)
    user = db.session.scalar(stmt)

    if not user:
        return jsonify({"error": "User not found."}), 404

    changed_fields = []
    role_was_changed = False

    if "role" in payload:
        try:
            role_enum = RoleName(payload["role"])
        except ValueError:
            return jsonify({"error": "Invalid role specified."}), 400

        role_stmt = sa.select(Role).filter_by(role_name=role_enum)
        role = db.session.scalar(role_stmt)

        if not role:
            return jsonify({"error": "Invalid role specified."}), 400

        user.role_id = role.id
        changed_fields.append("role")
        role_was_changed = True

    if "is_active" in payload:
        user.is_active = payload["is_active"]
        changed_fields.append("is_active")

    if "is_locked" in payload:
        user.is_locked = payload["is_locked"]

        if payload["is_locked"] is False:
            user.failed_login_count = 0

        changed_fields.append("is_locked")

    if "department" in payload:
        user.department = payload["department"]
        changed_fields.append("department")

    if "license_number" in payload:
        user.license_number = payload["license_number"]
        changed_fields.append("license_number")

    if not changed_fields:
        return jsonify({"error": "No recognized fields provided to update."}), 400

    db.session.commit()

    # Role changes get their own specific audit action, since privilege
    # escalation is the most sensitive thing this route can do. Every
    # other field change is logged under the generic user_updated action.
    action = AuditAction.role_changed if role_was_changed else AuditAction.user_updated

    log_access(
        user=current_user,
        action=action.value,
        status="Success",
        request=request,
        record_id=None,
        details=f"Fields updated: {', '.join(changed_fields)}",
    )

    return (
        jsonify(
            {
                "id": user.id,
                "message": "User updated",
                "fields_updated": changed_fields,
            }
        ),
        200,
    )


@auth_bp.route("/users", methods=["POST"])
@jwt_required()
@role_required([RoleName.admin])
def create_staff_user():
    new_staff_payload = request.get_json()

    if not new_staff_payload:
        return (
            jsonify(
                {
                    "error": "Missing payload: ensure you provide all required registration fields."
                }
            ),
            400,
        )

    columns_required = (
        "first_name" not in new_staff_payload
        or "last_name" not in new_staff_payload
        or "email" not in new_staff_payload
        or "password" not in new_staff_payload
        or "role" not in new_staff_payload
    )

    if columns_required:
        return (
            jsonify(
                {
                    "error": "Missing payload: ensure you provide all required registration fields."
                }
            ),
            400,
        )

    is_valid, email_result = is_valid_email(new_staff_payload["email"])
    if not is_valid:
        return jsonify({"error": "Invalid email format provided."}), 400

    new_staff_payload["email"] = email_result  # normalized form

    requested_role = new_staff_payload["role"]
    if requested_role == RoleName.patient.value:
        return (
            jsonify(
                {"error": "Patient accounts must self register through /auth/register."}
            ),
            400,
        )

    try:
        role_enum = RoleName(requested_role)
    except ValueError:
        return jsonify({"error": "Invalid role provided."}), 400

    email_exists = User.query.filter_by(email=new_staff_payload["email"]).first()
    if email_exists:
        return (
            jsonify({"error": "Email already exists, try using a different one."}),
            400,
        )

    hashed_password = bcrypt.generate_password_hash(
        new_staff_payload["password"]
    ).decode("utf-8")

    stmt = sa.select(Role.id).filter_by(role_name=role_enum)
    staff_role_id = db.session.scalar(stmt)
    if staff_role_id is None:
        return jsonify({"error": "Invalid role provided."}), 400

    role_id: int = staff_role_id

    staff = User()
    staff.first_name = new_staff_payload["first_name"]
    staff.last_name = new_staff_payload["last_name"]
    staff.email = new_staff_payload["email"]
    staff.password_hash = hashed_password
    staff.role_id = role_id
    staff.department = new_staff_payload.get("department")
    staff.license_number = new_staff_payload.get("license_number")

    db.session.add(staff)
    db.session.commit()

    log_access(
        user=current_user,
        action=AuditAction.user_created.value,
        status="Success",
        request=request,
        record_id=None,
        details=f"Staff account created with role {role_enum.value}",
    )

    return jsonify({"user_id": staff.id, "message": "Staff account created"}), 201


@auth_bp.route("/users", methods=["GET"])
@jwt_required()
@role_required([RoleName.admin])
def list_staff_users():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)

    if page < 1:
        page = 1
    if limit < 1:
        limit = 10

    offset = (page - 1) * limit

    role_stmt = sa.select(Role.id).filter_by(role_name=RoleName.patient)
    patient_role_id = db.session.scalar(role_stmt)

    if patient_role_id is None:
        return jsonify({"error": "Patient role is not configured."}), 500

    where_clause = User.role_id != patient_role_id
    count_stmt = sa.select(sa.func.count()).select_from(User).where(where_clause)
    total_users = db.session.scalar(count_stmt) or 0

    stmt = (
        sa.select(User)
        .where(where_clause)
        .order_by(User.id.desc())
        .limit(limit)
        .offset(offset)
    )
    staff_users = db.session.scalars(stmt).all()

    has_more = (offset + len(staff_users)) < total_users

    return (
        jsonify(
            {
                "total": total_users,
                "page": page,
                "limit": limit,
                "has_more": has_more,
                "users": [user.to_dict() for user in staff_users],
            }
        ),
        200,
    )
