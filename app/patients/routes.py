from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, current_user
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app import system as core
from app.extensions import db, bcrypt
from app.auth import User
from app.patients import Patient, PatientStatus

from app.patients.schemas import (
    PatientResponseSchema,
    PatientUpdateSchema,
    PatientListItemSchema,
)

bp = Blueprint("patient", __name__)


@bp.route("/", methods=["POST"])
@jwt_required()
@core.permission_required(core.PermissionAction.register_patient)
def register_patient():
    payload = request.get_json()
    if not payload:
        return jsonify({"error": "Missing payload: patient details are required."}), 400

    if "full_name" in payload and payload["full_name"]:
        name_parts = payload["full_name"].strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""
    else:
        first_name = payload.get("first_name")
        last_name = payload.get("last_name")

    age = payload.get("age")

    if not first_name or not last_name or age is None:
        return (
            jsonify({"error": "Missing payload: name and age are required."}),
            400,
        )

    national_id = payload.get("national_id")

    if national_id:
        existing = Patient.query.filter_by(national_id=national_id).first()
        if existing:
            core.log_access(
                action=core.AuditAction.patient_created,
                status="Failed",
                request=request,
                user=current_user,
                details=(
                    f"Rejected duplicate patient creation, national_id "
                    f"already exists for hospital_id {existing.hospital_id}."
                ),
            )
            return (
                jsonify(
                    {
                        "error": "A patient with this national ID already exists.",
                        "patient_id": str(existing.id),
                        "hospital_id": existing.hospital_id,
                    }
                ),
                409,
            )

    phone = payload.get("phone")
    possible_match = None
    if phone:
        possible_match = Patient.query.filter_by(
            first_name=first_name, last_name=last_name, age=age, phone=phone
        ).first()

    patient = Patient()
    patient.first_name = first_name
    patient.last_name = last_name
    patient.age = age
    patient.gender = payload.get("gender")
    patient.phone = phone
    patient.address = payload.get("address")
    patient.national_id = national_id
    patient.assigned_doctor_id = payload.get("assigned_doctor_id")
    patient.blood_group = payload.get("blood_group")
    patient.ward = payload.get("ward")

    db.session.add(patient)
    db.session.flush()

    next_val = db.session.execute(
        sa.text("SELECT nextval('patient_hospital_id_seq')")
    ).scalar()
    patient.hospital_id = f"MR-{next_val:06d}"

    core.log_access(
        user=current_user,
        action=core.AuditAction.patient_created,
        status="Success",
        request=request,
        record_id=None,
        details=f"Patient {patient.hospital_id} created",
    )

    if possible_match:
        core.log_access(
            user=current_user,
            action=core.AuditAction.duplicate_patient_warning,
            status="Review",
            request=request,
            record_id=None,
            details=(
                f"New patient {patient.hospital_id} matched existing "
                f"patient {possible_match.hospital_id} on name, age, "
                f"and phone"
            ),
        )

    response = {
        "patient_id": str(patient.id),
        "hospital_id": patient.hospital_id,
        "message": "Patient record created",
    }
    if possible_match:
        response["duplicate_warning"] = (
            f"A similar existing patient record was found, hospital_id "
            f"{possible_match.hospital_id}. Please verify this is not a "
            f"duplicate entry."
        )

    return jsonify(response), 201


@bp.route("/<uuid:patient_id>/portal-access", methods=["POST"])
@jwt_required()
@core.permission_required(core.PermissionAction.link_patient_identity)
def grant_portal_access(patient_id):
    payload = request.get_json()
    if not payload or "portal_email" not in payload or "portal_password" not in payload:
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Failed",
            request=request,
            user=current_user,
            details="Rejected portal access grant, missing portal_email or portal_password.",
        )
        return (
            jsonify(
                {
                    "error": "Missing payload: portal_email and portal_password are required."
                }
            ),
            400,
        )

    patient = Patient.query.get(patient_id)
    if not patient:
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected portal account creation, patient {patient_id} not found.",
        )
        return jsonify({"error": "Patient record not found."}), 404

    existing_portal_user = db.session.scalar(
        sa.select(User).where(User.patient_id == patient.id)
    )

    if existing_portal_user:
        return jsonify({"error": "This patient already has portal access."}), 409

    portal_email = payload["portal_email"]
    portal_password = payload["portal_password"]

    is_valid, email_result = core.is_valid_email(portal_email)
    if not is_valid:
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected portal account creation, invalid portal_email format: {portal_email}",
        )
        return jsonify({"error": "Invalid email format provided."}), 400

    portal_email = email_result  # normalized form, e.g. lowercased/canonicalized

    email_exists = User.query.filter_by(email=portal_email).first()
    if email_exists:
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected portal account creation, portal_email already registered: {portal_email}",
        )
        return (
            jsonify({"error": "This email is already registered to another account."}),
            409,
        )

    stmt = sa.select(core.Role.id).filter_by(role_name=core.RoleName.patient)
    patient_role_id = db.session.scalar(stmt)
    if patient_role_id is None:
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Error",
            request=request,
            user=current_user,
            details="Patient role is not configured in the roles table.",
        )
        return jsonify({"error": "Patient role is not configured."}), 500

    portal_user = User()
    portal_user.first_name = patient.first_name
    portal_user.last_name = patient.last_name
    portal_user.email = portal_email
    portal_user.password_hash = bcrypt.generate_password_hash(portal_password).decode(
        "utf-8"
    )
    portal_user.role_id = patient_role_id
    portal_user.patient_id = patient.id

    db.session.add(portal_user)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        core.log_access(
            action=core.AuditAction.patient_portal_linked.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected portal account creation, concurrent link detected for patient {patient_id}.",
        )
        return (
            jsonify(
                {
                    "error": "This patient was just linked to an account by another request. Please retry."
                }
            ),
            409,
        )

    core.log_access(
        user=current_user,
        action=core.AuditAction.patient_portal_linked.value,
        status="Success",
        request=request,
        record_id=None,
        details=f"Portal access granted for patient {patient.hospital_id}",
    )

    return (
        jsonify(
            {
                "user_id": portal_user.id,
                "patient_id": str(patient.id),
                "message": "Portal access granted successfully",
            }
        ),
        201,
    )


@bp.route("/", methods=["GET"])
@jwt_required()
@core.permission_required(core.PermissionAction.view_patients)
def list_patients():
    search = request.args.get("search", "").strip()
    hospital_id = request.args.get("hospital_id")

    stmt = sa.select(Patient)

    if hospital_id:
        stmt = stmt.where(Patient.hospital_id == hospital_id)
    elif search:
        like = f"%{search}%"
        stmt = stmt.where(
            sa.or_(
                Patient.first_name.ilike(like),
                Patient.last_name.ilike(like),
                Patient.national_id.ilike(like),
                Patient.phone.ilike(like),
                Patient.hospital_id.ilike(like),
                sa.func.concat(Patient.first_name, " ", Patient.last_name).ilike(like),
            )
        )

    unlinked = request.args.get("unlinked", "").lower() == "true"
    if unlinked:
        if current_user.role.role_name not in (
            core.RoleName.admin,
            core.RoleName.records_officer,
        ):
            core.log_access(
                action=core.AuditAction.permission_denied,
                status="Failed",
                request=request,
                user=current_user,
                details="Role rejected for unlinked-patients filter on list_patients.",
            )
            return (
                jsonify({"error": "Access denied: insufficient role permissions."}),
                403,
            )
        stmt = stmt.where(
            ~sa.select(User.id).where(User.patient_id == Patient.id).exists()
        )

    total = db.session.scalar(
            sa.select(sa.func.count()).select_from(stmt.subquery())
        )

    page = max(request.args.get("page", 1, type=int), 1)
    limit = min(max(request.args.get("limit", 20, type=int), 1), 100)

    stmt = (
        stmt.order_by(Patient.created_at.desc()).limit(limit).offset((page - 1) * limit)
    )
    patients = db.session.execute(stmt).scalars().all()

    core.log_access(
        user=current_user,
        action=core.AuditAction.patient_list_viewed,
        status="Success",
        request=request,
    )
    patient_list_schema = PatientListItemSchema(many=True)

    return (
        jsonify(
            {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": (total + limit - 1) // limit if total else 1,
                "patients": patient_list_schema.dump(patients),
            }
        ),
        200,
    )

@bp.route("/<uuid:patient_id>", methods=["GET"])
@jwt_required()
@core.permission_required(core.PermissionAction.view_patients)
def get_patient(patient_id):
    patient = db.session.get(Patient, patient_id)

    if not patient:
        core.log_access(
            user=current_user,
            action=core.AuditAction.patient_viewed,
            status="Blocked",
            request=request,
            details=f"Patient {patient_id} not found.",
        )
        return jsonify({"error": "Patient record not found."}), 404

    core.log_access(
        user=current_user,
        action=core.AuditAction.patient_viewed,
        status="Success",
        request=request,
    )

    patient_response_schema = PatientResponseSchema()
    return jsonify(patient_response_schema.dump(patient)), 200


@bp.route("/<uuid:patient_id>", methods=["PATCH"])
@jwt_required()
@core.permission_required(core.PermissionAction.edit_patients)
def update_patient(patient_id):
    patient = db.session.get(Patient, patient_id)
    if not patient:
        return jsonify({"error": "Patient record not found."}), 404

    payload = request.get_json()
    if not payload:
        return jsonify({"error": "No fields provided."}), 400

    if "status" in payload:
        try:
            payload["status"] = PatientStatus(payload["status"]).value
        except ValueError:
            core.log_access(
                action=core.AuditAction.patient_updated,
                status="failed",
                request=request,
                user=current_user,
                details=f"Invalid status value submitted: {payload['status']}",
            )
            return (
                jsonify(
                    {"error": f"Invalid status value submitted: {payload['status']}"}
                ),
                400,
            )

    patient_update_schema = PatientUpdateSchema()
    errors = patient_update_schema.validate(payload, partial=True)
    if errors:
        return jsonify({"error": errors}), 400

    changed_fields = []
    for field, value in payload.items():
        if field in patient_update_schema.fields:
            setattr(patient, field, value)
            changed_fields.append(field)

    if not changed_fields:
        return jsonify({"error": "No valid fields provided."}), 400

    db.session.commit()
    core.log_access(
        user=current_user,
        action=core.AuditAction.patient_updated,
        status="Success",
        request=request,
        details=f"Fields updated: {', '.join(changed_fields)}",
    )

    patient_response_schema = PatientResponseSchema()
    return jsonify(patient_response_schema.dump(patient)), 200
