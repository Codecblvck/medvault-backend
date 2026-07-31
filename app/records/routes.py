import json
import hashlib
import uuid
import sqlalchemy as sa

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, current_user


from app.extensions import db, bcrypt
from app.access_control import (
    can_upload_record_type,
    permission_required,
    role_required,
    PermissionAction,
    RoleName,
    Role,
)
from app.audit import log_access, AuditAction
from app.auth import User, is_valid_email
from app.records import Record, RecordType, Patient
from app.encryption.aes_utils import encrypt_data, decrypt_data
from app.storage.minio_client import upload_file, get_file_url, delete_file

records_bp = Blueprint("record", __name__)


@records_bp.route("/patients", methods=["POST"])
@jwt_required()
@role_required(
    [RoleName.admin, RoleName.doctor, RoleName.nurse, RoleName.records_officer]
)
def create_patient():
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
            log_access(
                action=AuditAction.patient_created,
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

    portal_email = payload.get("portal_email")
    portal_password = payload.get("portal_password")

    if portal_email and not is_valid_email(portal_email):
        log_access(
            action=AuditAction.patient_created,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient creation, invalid portal_email format: {portal_email}",
        )
        return jsonify({"error": "Invalid email format provided."}), 400

    patient = Patient()
    patient.first_name = first_name
    patient.last_name = last_name
    patient.age = age
    patient.gender = payload.get("gender")
    patient.phone = phone
    patient.address = payload.get("address")
    patient.national_id = national_id
    patient.assigned_doctor_id = payload.get("assigned_doctor_id")

    db.session.add(patient)
    db.session.flush()

    next_val = db.session.execute(
        sa.text("SELECT nextval('patient_hospital_id_seq')")
    ).scalar()
    patient.hospital_id = f"MR-{next_val:06d}"

    account_message = None

    if portal_email and portal_password:
        email_exists = User.query.filter_by(email=portal_email).first()
        if email_exists:
            db.session.rollback()
            log_access(
                action=AuditAction.patient_created,
                status="Failed",
                request=request,
                user=current_user,
                details=f"Rejected patient creation, portal_email already registered: {portal_email}",
            )
            return (
                jsonify(
                    {"error": "This email is already registered to another account."}
                ),
                400,
            )

        stmt = sa.select(Role.id).filter_by(role_name=RoleName.patient)
        patient_role_id = db.session.scalar(stmt)
        if patient_role_id is None:
            db.session.rollback()
            log_access(
                action=AuditAction.patient_created,
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
        portal_user.password_hash = bcrypt.generate_password_hash(
            portal_password
        ).decode("utf-8")
        portal_user.role_id = patient_role_id
        portal_user.patient_id = patient.id

        db.session.add(portal_user)
        account_message = "Portal account created and linked"

    db.session.commit()

    log_access(
        user=current_user,
        action=AuditAction.patient_created,
        status="Success",
        request=request,
        record_id=None,
        details=f"Patient {patient.hospital_id} created",
    )

    if possible_match:
        log_access(
            user=current_user,
            action=AuditAction.duplicate_patient_warning,
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
    if account_message:
        response["portal_account"] = account_message
    if possible_match:
        response["duplicate_warning"] = (
            f"A similar existing patient record was found, hospital_id "
            f"{possible_match.hospital_id}. Please verify this is not a "
            f"duplicate entry."
        )

    return jsonify(response), 201


@records_bp.route("/patients/<uuid:patient_id>/link", methods=["PATCH"])
@jwt_required()
@role_required([RoleName.admin, RoleName.records_officer])
def link_patient_account(patient_id):
    payload = request.get_json()
    if not payload or "user_id" not in payload:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details="Rejected patient account link, missing user_id in payload.",
        )
        return jsonify({"error": "Missing payload: user_id is required."}), 400

    patient = Patient.query.get(patient_id)
    if not patient:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient account link, patient {patient_id} not found.",
        )
        return jsonify({"error": "Patient record not found."}), 404

    user = User.query.get(payload["user_id"])
    if not user:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient account link, user {payload['user_id']} not found.",
        )
        return jsonify({"error": "User account not found."}), 404

    if user.role.role_name != RoleName.patient:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient account link, user {user.id} is not a patient role account.",
        )
        return (
            jsonify(
                {"error": "Only patient accounts can be linked to a patient record."}
            ),
            400,
        )

    if user.patient_id is not None:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient account link, user {user.id} already linked to a patient record.",
        )
        return (
            jsonify(
                {"error": "This user account is already linked to a patient record."}
            ),
            400,
        )

    existing_link = User.query.filter_by(patient_id=patient_id).first()
    if existing_link:
        log_access(
            action=AuditAction.user_updated.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected patient account link, patient {patient_id} already linked to another account.",
        )
        return (
            jsonify(
                {"error": "This patient record is already linked to another account."}
            ),
            400,
        )

    user.patient_id = patient.id
    db.session.commit()

    log_access(
        user=current_user,
        action=AuditAction.user_updated.value,
        status="Success",
        request=request,
        record_id=None,
        details=f"Linked user {user.id} to patient {patient.id}",
    )

    return (
        jsonify(
            {
                "user_id": user.id,
                "patient_id": str(patient.id),
                "message": "Patient account linked successfully",
            }
        ),
        200,
    )


@records_bp.route("", methods=["GET"])
@jwt_required()
@permission_required(PermissionAction.view_records)
def list_records():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    offset = (page - 1) * limit

    stmt = sa.select(Record)
    count_stmt = sa.select(sa.func.count()).select_from(Record)

    if current_user.role.role_name == RoleName.patient:
        if current_user.patient_id is None:
            log_access(
                action=AuditAction.record_viewed.value,
                status="Blocked",
                request=request,
                user=current_user,
                details="Patient account has no linked patient identity, cannot list records.",
            )
            return jsonify({"error": "No linked patient record found."}), 403
        stmt = stmt.where(Record.patient_id == current_user.patient_id)
        count_stmt = count_stmt.where(Record.patient_id == current_user.patient_id)

    patient_id_param = request.args.get("patient_id")
    if patient_id_param:
        try:
            patient_id_uuid = uuid.UUID(patient_id_param)
        except ValueError:
            log_access(
                action=AuditAction.record_viewed.value,
                status="Failed",
                request=request,
                user=current_user,
                details=f"Malformed patient_id filter supplied: {patient_id_param}",
            )
            return (
                jsonify({"error": f"Malformed patient_id value: {patient_id_param}"}),
                400,
            )
        stmt = stmt.where(Record.patient_id == patient_id_uuid)
        count_stmt = count_stmt.where(Record.patient_id == patient_id_uuid)

    record_type_param = request.args.get("record_type")
    if record_type_param:
        try:
            record_type_enum = RecordType(record_type_param)
        except ValueError:
            log_access(
                action=AuditAction.record_viewed.value,
                status="Failed",
                request=request,
                user=current_user,
                details=f"Invalid record_type filter supplied: {record_type_param}",
            )
            return (
                jsonify({"error": f"Invalid record_type value: {record_type_param}"}),
                400,
            )
        stmt = stmt.where(Record.record_type == record_type_enum)
        count_stmt = count_stmt.where(Record.record_type == record_type_enum)

    date_from = request.args.get("date_from")
    if date_from:
        stmt = stmt.where(Record.created_at >= date_from)
        count_stmt = count_stmt.where(Record.created_at >= date_from)

    date_to = request.args.get("date_to")
    if date_to:
        stmt = stmt.where(Record.created_at <= date_to)
        count_stmt = count_stmt.where(Record.created_at <= date_to)

    total = db.session.scalar(count_stmt) or 0

    stmt = stmt.order_by(Record.created_at.desc()).limit(limit).offset(offset)
    records = db.session.execute(stmt).scalars().all()

    has_more = (offset + len(records)) < total

    log_access(
        action=AuditAction.record_viewed.value,
        status="Success",
        request=request,
        user=current_user,
        details=f"Listed records, page {page}, limit {limit}, {len(records)} returned.",
    )

    return (
        jsonify(
            {
                "total": total,
                "page": page,
                "limit": limit,
                "has_more": has_more,
                "records": [
                    {
                        "id": str(r.id),
                        "patient_name": r.patient.full_name,
                        "record_type": r.record_type.value,
                        "uploaded_by_name": r.uploader.full_name,
                        "department": r.department,
                        "file_size": r.file_size,
                        "created_at": r.created_at.isoformat() + "Z",
                    }
                    for r in records
                ],
            }
        ),
        200,
    )


@records_bp.route("/upload", methods=["POST"])
@jwt_required()
@permission_required(PermissionAction.upload_records)
def upload_records():
    user = current_user

    patient_id = request.form.get("patient_id")
    record_type_str = request.form.get("record_type")
    data_str = request.form.get("data")

    if not patient_id or not record_type_str or not data_str:
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details="Missing required payload fields: patient_id, record_type, or data.",
        )
        return (
            jsonify(
                {
                    "error": "Missing payload: ensure you provide patient_id, record_type, and data."
                }
            ),
            400,
        )

    try:
        record_type_enum = RecordType(record_type_str)
    except ValueError:
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details=f"Invalid record_type value submitted: {record_type_str}",
        )
        return (
            jsonify(
                {"error": f"Invalid record_type value submitted: {record_type_str}"}
            ),
            400,
        )

    try:
        patient_uuid = uuid.UUID(patient_id)
    except ValueError:
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details=f"Malformed patient_id UUID pattern: {patient_id}",
        )
        return (
            jsonify({"error": f"Malformed patient_id UUID pattern: {patient_id}"}),
            400,
        )

    if not user or not can_upload_record_type(user.role.role_name, record_type_enum):
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details="Access denied: insufficient role permissions for this record type.",
        )
        return (
            jsonify(
                {
                    "error": "Access denied: insufficient role permissions for this record type."
                }
            ),
            403,
        )

    try:
        data_dict = json.loads(data_str)
    except json.JSONDecodeError:
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details="The metadata 'data' string was not a structurally valid JSON dictionary.",
        )
        return (
            jsonify(
                {
                    "error": "The metadata 'data' string was not a structurally valid JSON dictionary."
                }
            ),
            400,
        )

    json_byte = json.dumps(data_dict).encode("utf-8")
    checksum = hashlib.sha256(json_byte).hexdigest()
    encrypted_str, wrapped_key_str = encrypt_data(data_dict)

    uploaded_file = request.files.get("file")
    object_key = None
    file_size = None
    record_id = uuid.uuid4()

    if uploaded_file:
        object_key = f"records/{patient_uuid}/{record_id}_{uploaded_file.filename}"

        uploaded_file.stream.seek(0, 2)
        file_size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0)

        

    record = Record()
    record.id = record_id
    record.patient_id = patient_uuid
    record.uploaded_by = user.id
    record.record_type = record_type_enum
    record.checksum = checksum
    record.encrypted_data = encrypted_str
    record.encrypted_aes_key = wrapped_key_str
    record.file_path = object_key
    record.file_size = file_size


    try:
        db.session.add(record)
        db.session.flush()
        
        if uploaded_file:
            upload_file(uploaded_file, object_key)
        db.session.commit()  
    except RuntimeError as minio_error:
        db.session.rollback()
        log_access(
            action=AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details=f"File upload failed, record was not saved: {minio_error}",
        )
        return (
            jsonify({"error": f"File upload failed, record was not saved: {minio_error}"}),
                            502,
        )
      
    except Exception as db_error:
        db.session.rollback()
        if uploaded_file and object_key:
            try:
                delete_file(object_key)
            except Exception:
                pass

        log_access(
            action=AuditAction.record_uploaded.value,
            status="Error",
            request=request,
            user=user,
            details=f"Database commit transaction failure: {str(db_error)}",
        )

        return (
            jsonify(
                {"error": "Database persistence failure occurred. Upload reverted."}
            ),
            500,
        )

    log_access(
        action=AuditAction.record_uploaded.value,
        status="Success",
        request=request,
        user=user,
        record_id=record.id,
        details="Record uploaded and encrypted successfully.",
    )

    return (
        jsonify(
            {
                "record_id": str(record.id),
                "checksum": checksum,
                "message": "Record uploaded successfully.",
            }
        ),
        201,
    )


@records_bp.route("/<uuid:record_id>", methods=["GET"])
@jwt_required()
@permission_required(PermissionAction.view_records)
def view_record(record_id):
    record = Record.query.get(record_id)
    if not record:
        log_access(
            action=AuditAction.record_viewed.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Requested record {record_id} does not exist.",
        )
        return jsonify({"error": "Patient record not found."}), 404

    if current_user.role.role_name == RoleName.patient:
        if (
            current_user.patient_id is None
            or record.patient_id != current_user.patient_id
        ):
            log_access(
                action=AuditAction.record_viewed.value,
                status="Blocked",
                request=request,
                user=current_user,
                record_id=record.id,
                details="Patient attempted to view a record outside their own linked patient identity.",
            )
            return jsonify({"error": "You are not permitted to view this record."}), 403

    decrypted_data = decrypt_data(record.encrypted_data, record.encrypted_aes_key)
    json_bytes = json.dumps(decrypted_data).encode("utf-8")
    computed_checksum = hashlib.sha256(json_bytes).hexdigest()

    if computed_checksum != record.checksum:
        log_access(
            action=AuditAction.record_viewed.value,
            status="Error",
            request=request,
            user=current_user,
            record_id=record.id,
            details="Checksum mismatch on retrieval, possible data corruption or tampering.",
        )
        return jsonify({"error": "Data integrity verification failed."}), 500

    file_url = None
    if record.file_path:
        try:
            file_url = get_file_url(record.file_path)
        except RuntimeError:
            file_url = None

    log_access(
        action=AuditAction.record_viewed.value,
        status="Success",
        request=request,
        user=current_user,
        record_id=record.id,
        details="Record decrypted and viewed successfully.",
    )

    return jsonify(
        {
            "id": str(record.id),
            "patient_id": str(record.patient_id),
            "patient_name": record.patient.full_name,
            "record_type": record.record_type.value,
            "uploaded_by_name": record.uploader.full_name,
            "department": record.department,
            "data": decrypted_data,
            "checksum": record.checksum,
            "file_path": record.file_path,
            "file_url": file_url,
            "created_at": str(record.created_at),
        }
    )
