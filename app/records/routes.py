import json
import hashlib
import uuid
import sqlalchemy as sa

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required, current_user

from app.extensions import db, bcrypt
from app import system as core
from app.patients import Patient
from app.records import Record, RecordType

bp = Blueprint("record", __name__)


# RECORD
@bp.route("/", methods=["GET"])
@jwt_required()
@core.permission_required(core.PermissionAction.view_records)
def read_records():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=10, type=int)
    if page < 1:
        page = 1
    if limit < 1:
        limit = 10
    offset = (page - 1) * limit

    stmt = sa.select(Record)
    count_stmt = sa.select(sa.func.count()).select_from(Record)

    if current_user.role.role_name == core.RoleName.patient:
        if current_user.patient_id is None:
            core.log_access(
                action=core.AuditAction.record_viewed.value,
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
            core.log_access(
                action=core.AuditAction.record_viewed.value,
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
            core.log_access(
                action=core.AuditAction.record_viewed.value,
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

    core.log_access(
        action=core.AuditAction.record_viewed.value,
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
                        "patient_id": str(r.patient_id),
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


@bp.route("/stats", methods=["GET"])
@jwt_required()
@core.role_required(
    [
        core.RoleName.admin,
        core.RoleName.records_officer,
        core.RoleName.doctor,
        core.RoleName.lab_technician,
        core.RoleName.patient,
    ]
)
def record_stats():
    role = current_user.role.role_name

    # Base statements, scope narrowed per role below before execution
    total_stmt = sa.select(sa.func.count()).select_from(Record)
    attachment_stmt = (
        sa.select(sa.func.count())
        .select_from(Record)
        .where(Record.file_path.is_not(None))
    )
    size_stmt = sa.select(
        sa.func.coalesce(sa.func.sum(Record.file_size), 0)
    ).select_from(Record)
    type_stmt = sa.select(Record.record_type, sa.func.count(Record.id)).group_by(
        Record.record_type
    )

    if role in (core.RoleName.admin, core.RoleName.records_officer):
        # Hospital-wide, unscoped, matches their explicit permission
        pass

    elif role == core.RoleName.patient:
        if current_user.patient_id is None:
            return jsonify({"error": "No linked patient record found."}), 403
        scope = Record.patient_id == current_user.patient_id
        total_stmt = total_stmt.where(scope)
        attachment_stmt = attachment_stmt.where(scope)
        size_stmt = size_stmt.where(scope)
        type_stmt = type_stmt.where(scope)

    elif role == core.RoleName.doctor:
        # Scoped to records belonging to this doctor's assigned patients,
        # not records they personally uploaded, per FR-2.2 (assigned patients).
        scope = Record.patient_id.in_(
            sa.select(Patient.id).where(Patient.assigned_doctor_id == current_user.id)
        )
        total_stmt = total_stmt.where(scope)
        attachment_stmt = attachment_stmt.where(scope)
        size_stmt = size_stmt.where(scope)
        type_stmt = type_stmt.where(scope)

    elif role == core.RoleName.lab_technician:
        # Scoped to records this lab technician personally uploaded,
        # the only implementable reading of "linked records" today.
        scope = Record.uploaded_by == current_user.id
        total_stmt = total_stmt.where(scope)
        attachment_stmt = attachment_stmt.where(scope)
        size_stmt = size_stmt.where(scope)
        type_stmt = type_stmt.where(scope)

    total_records = db.session.scalar(total_stmt) or 0
    attachment_count = db.session.scalar(attachment_stmt) or 0
    total_file_size = db.session.scalar(size_stmt) or 0
    record_type_counts = {
        record_type.value: count for record_type, count in db.session.execute(type_stmt)
    }

    return (
        jsonify(
            {
                "total": total_records,
                "by_type": record_type_counts,
                "attachments": attachment_count,
                "storage": {
                    "used_bytes": total_file_size,
                },
            }
        ),
        200,
    )


@bp.route("/<uuid:record_id>", methods=["GET"])
@jwt_required()
@core.permission_required(core.PermissionAction.view_record_detail)
def read_record_detail(record_id):
    record = Record.query.get(record_id)
    if not record:
        core.log_access(
            action=core.AuditAction.record_viewed.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Requested record {record_id} does not exist.",
        )
        return jsonify({"error": "Patient record not found."}), 404

    if not core.can_view_record(current_user, record):
        core.log_access(
            action=core.AuditAction.record_viewed.value,
            status="Blocked",
            request=request,
            user=current_user,
            record_id=record.id,
            details="Patient attempted to view a record outside their own linked patient identity.",
        )
        return jsonify({"error": "You are not permitted to view this record."}), 403

    try:
        decrypted_data = core.decrypt_data(
            record.encrypted_data, record.encrypted_aes_key
        )
    except Exception:
        core.log_access(
            action=core.AuditAction.record_viewed.value,
            status="Error",
            request=request,
            user=current_user,
            record_id=record.id,
            details="Decryption failed, possible key mismatch or data corruption.",
        )
        return jsonify({"error": "Data integrity verification failed."}), 500

    json_bytes = json.dumps(decrypted_data).encode("utf-8")
    computed_checksum = hashlib.sha256(json_bytes).hexdigest()

    if computed_checksum != record.checksum:
        core.log_access(
            action=core.AuditAction.record_viewed.value,
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
            file_url = core.get_file_url(record.file_path)
        except RuntimeError:
            file_url = None

    core.log_access(
        action=core.AuditAction.record_viewed.value,
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


@bp.route("/upload", methods=["POST"])
@jwt_required()
@core.permission_required(core.PermissionAction.upload_records)
def upload_records():
    user = current_user

    patient_id = request.form.get("patient_id")
    record_type_str = request.form.get("record_type")
    data_str = request.form.get("data")
    department = request.form.get("department")

    if not patient_id or not record_type_str or not data_str:
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
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
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
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
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details=f"Malformed patient_id UUID pattern: {patient_id}",
        )
        return (
            jsonify({"error": f"Malformed patient_id UUID pattern: {patient_id}"}),
            400,
        )

    if not user or not core.can_upload_record_type(
        user.role.role_name, record_type_enum
    ):
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
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
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
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
    encrypted_str, wrapped_key_str = core.encrypt_data(data_dict)

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
    record.department = department
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
            core.upload_file(uploaded_file, object_key)
        db.session.commit()
    except RuntimeError as minio_error:
        db.session.rollback()
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=user,
            details=f"File upload failed, record was not saved: {minio_error}",
        )
        return (
            jsonify(
                {"error": f"File upload failed, record was not saved: {minio_error}"}
            ),
            502,
        )

    except Exception as db_error:
        db.session.rollback()
        if uploaded_file and object_key:
            try:
                core.delete_file(object_key)
            except Exception:
                pass

        core.log_access(
            action=core.AuditAction.record_uploaded.value,
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

    core.log_access(
        action=core.AuditAction.record_uploaded.value,
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


@bp.route("/<uuid:record_id>/attach-file", methods=["PATCH"])
@jwt_required()
@core.permission_required(core.PermissionAction.upload_records)
def attach_file_to_record(record_id):
    record = Record.query.get(record_id)
    if not record:
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=current_user,
            details=f"Rejected file attach, record {record_id} not found.",
        )
        return jsonify({"error": "Record not found."}), 404

    if record.file_path is not None:
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=current_user,
            record_id=record.id,
            details="Rejected file attach, record already has an attached file.",
        )
        return jsonify({"error": "This record already has a file attached."}), 400

    if not core.can_upload_record_type(current_user.role.role_name, record.record_type):
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=current_user,
            record_id=record.id,
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

    uploaded_file = request.files.get("file")
    if not uploaded_file:
        return jsonify({"error": "Missing payload: file is required."}), 400

    object_key = f"records/{record.patient_id}/{record.id}_{uploaded_file.filename}"

    uploaded_file.stream.seek(0, 2)
    file_size = uploaded_file.stream.tell()
    uploaded_file.stream.seek(0)

    try:
        core.upload_file(uploaded_file, object_key)
    except RuntimeError as minio_error:
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Failed",
            request=request,
            user=current_user,
            record_id=record.id,
            details=f"File attach failed, storage unreachable: {minio_error}",
        )
        return jsonify({"error": f"File upload failed: {minio_error}"}), 502

    record.file_path = object_key
    record.file_size = file_size

    try:
        db.session.commit()
    except Exception as db_error:
        db.session.rollback()
        try:
            core.delete_file(object_key)
        except Exception:
            pass
        core.log_access(
            action=core.AuditAction.record_uploaded.value,
            status="Error",
            request=request,
            user=current_user,
            record_id=record.id,
            details=f"Database commit failure during file attach: {db_error}",
        )
        return (
            jsonify(
                {"error": "Database persistence failure occurred. Attachment reverted."}
            ),
            500,
        )

    core.log_access(
        action=core.AuditAction.record_uploaded.value,
        status="Success",
        request=request,
        user=current_user,
        record_id=record.id,
        details="File attached to existing record.",
    )

    return (
        jsonify(
            {
                "record_id": str(record.id),
                "file_path": record.file_path,
                "message": "File attached successfully.",
            }
        ),
        200,
    )
