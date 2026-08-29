"""
Seeds the synthetic medical records dataset
(seeds/medvault_synthetic_medical_records_1500.csv) into the database.

Runs after seed_patients.py and seed_staff.py, needs both patients and
staff to already exist.

Idempotent by design: checksum is computed the same way the live upload
route computes it, sha256 of json.dumps(data_dict) with no sort_keys, on
the exact dict parsed from the CSV's data_json column. Paired with
patient_id, that (patient_id, checksum) pair is the natural key checked
before every insert.

Two things this script deliberately does NOT take from the CSV, and why:

  uploaded_by_role is "doctor" for all 1500 rows, including Vitals and
  Clinical Notes, which UPLOAD_TYPE_PERMISSIONS does not allow a doctor
  to upload. Trusting it as-is would seed records the live system could
  never have produced under its own rules. Instead, each record_type is
  mapped to the one role that would realistically and permissibly upload
  it (see RECORD_TYPE_TO_ROLE below). Lab Report is technically permitted
  for both doctor and lab_technician, lab_technician is used as the more
  realistic uploader.

  file_name is decorative, no real file exists in object storage for it
  to point to. file_path and file_size are left null, same as any record
  created today without an attachment.

created_at is explicitly set from the CSV's record_date, confirmed
deliberately, so the seeded dataset has a realistic spread of dates
instead of 1500 records all dated the moment this script was run.

Run this once from the project root, python db_seed/seed_records.py
Safe to run more than once. Requires RSA_PUBLIC_KEY_PATH to be configured,
same requirement as the live app.
"""

import csv
import hashlib
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlalchemy as sa

from app import create_app
from app import system as core
from app.extensions import db
from app.auth.models import User
from app.patients.models import Patient
from app.records.models import Record, RecordType

CSV_PATH = PROJECT_ROOT / "seeds" / "medvault_synthetic_medical_records_1500.csv"

REQUIRED_COLUMNS = {
    "record_reference", "patient_hospital_id", "record_type", "department",
    "record_date", "uploaded_by_role", "data_json",
}

# record_type -> the one role that realistically and permissibly uploads
# it. Confirmed against UPLOAD_TYPE_PERMISSIONS in app/system/access.py.
# Lab Report is technically valid for both doctor and lab_technician,
# lab_technician is the more realistic choice and is used here.
RECORD_TYPE_TO_ROLE = {
    RecordType.lab_report: core.RoleName.lab_technician,
    RecordType.imaging: core.RoleName.doctor,
    RecordType.prescription: core.RoleName.doctor,
    RecordType.discharge_summary: core.RoleName.doctor,
    RecordType.vitals: core.RoleName.nurse,
    RecordType.clinical_notes: core.RoleName.nurse,
}


def compute_checksum(data_dict):
    """
    Must match the live upload route exactly, sha256 of json.dumps with no
    sort_keys, on the same dict that gets encrypted. This is what makes
    checksum a valid, reproducible idempotency key across reruns.
    """
    json_bytes = json.dumps(data_dict).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest()


def resolve_record_basics(row, patient_id_by_hospital_id):
    """
    Everything needed to compute the idempotency key, cheap, no
    encryption. Raises ValueError on anything malformed or unresolvable.
    """
    hospital_id = row["patient_hospital_id"].strip()
    patient_id = patient_id_by_hospital_id.get(hospital_id)
    if patient_id is None:
        raise ValueError(f"no patient found with hospital_id '{hospital_id}'")

    try:
        record_type = RecordType(row["record_type"].strip())
    except ValueError:
        raise ValueError(
            f"record_type '{row['record_type']}' does not match any RecordType value"
        )

    try:
        data_dict = json.loads(row["data_json"])
    except json.JSONDecodeError as e:
        raise ValueError(f"data_json is not valid JSON: {e}")

    try:
        record_date = datetime.strptime(row["record_date"].strip(), "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"record_date '{row['record_date']}' is not YYYY-MM-DD")

    checksum = compute_checksum(data_dict)

    return patient_id, record_type, data_dict, record_date, checksum


def build_record(row, patient_id, record_type, data_dict, record_date, checksum,
                  staff_by_role, upload_counters):
    """
    The expensive half, only called once a row has already cleared the
    idempotency check. Picks an uploader and performs the actual
    encryption.
    """
    role_name = RECORD_TYPE_TO_ROLE[record_type]
    staff_list = staff_by_role.get(role_name) or []
    if not staff_list:
        raise ValueError(
            f"no staff with role '{role_name.value}' available to attribute "
            f"a {record_type.value} record to"
        )

    counter = upload_counters[role_name]
    uploader = staff_list[counter % len(staff_list)]
    upload_counters[role_name] += 1

    encrypted_data, encrypted_aes_key = core.encrypt_data(data_dict)

    record = Record()
    record.patient_id = patient_id
    record.uploaded_by = uploader.id
    record.record_type = record_type
    record.department = row["department"].strip() or None
    record.encrypted_data = encrypted_data
    record.encrypted_aes_key = encrypted_aes_key
    record.checksum = checksum
    record.created_at = record_date
    # file_path / file_size left null, see module docstring

    return record


def seed_records():
    app = create_app()

    with app.app_context():
        if not CSV_PATH.exists():
            print(f"CSV not found at {CSV_PATH}")
            return

        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing_columns:
                print(f"CSV is missing expected columns: {missing_columns}")
                return
            rows = list(reader)

        patient_id_by_hospital_id = {
            hospital_id: patient_id
            for hospital_id, patient_id in db.session.execute(
                sa.select(Patient.hospital_id, Patient.id)
            )
        }
        if not patient_id_by_hospital_id:
            print("No patients found. Run seed_patients.py first.")
            return

        staff_by_role = defaultdict(list)
        staff_stmt = (
            sa.select(User, core.Role.role_name)
            .join(core.Role, User.role_id == core.Role.id)
            .order_by(User.id)
        )
        for user, role_name in db.session.execute(staff_stmt):
            staff_by_role[role_name].append(user)

        if not any(staff_by_role.get(r) for r in RECORD_TYPE_TO_ROLE.values()):
            print("No relevant staff found. Run seed_staff.py first.")
            return

        existing_pairs = set(
            db.session.execute(sa.select(Record.patient_id, Record.checksum))
        )

        to_insert = []
        skipped_existing = 0
        skipped_bad_rows = []
        seen_in_this_run = set()
        upload_counters = Counter()

        for line_number, row in enumerate(rows, start=2):  # header is line 1
            try:
                patient_id, record_type, data_dict, record_date, checksum = (
                    resolve_record_basics(row, patient_id_by_hospital_id)
                )
            except ValueError as e:
                skipped_bad_rows.append((line_number, str(e)))
                continue

            pair = (patient_id, checksum)
            if pair in existing_pairs or pair in seen_in_this_run:
                skipped_existing += 1
                continue

            try:
                record = build_record(
                    row, patient_id, record_type, data_dict, record_date,
                    checksum, staff_by_role, upload_counters,
                )
            except ValueError as e:
                skipped_bad_rows.append((line_number, str(e)))
                continue

            to_insert.append(record)
            seen_in_this_run.add(pair)

        if to_insert:
            db.session.add_all(to_insert)
            db.session.commit()

        print(f"Rows in CSV:        {len(rows)}")
        print(f"Inserted:           {len(to_insert)}")
        print(f"Skipped (existing): {skipped_existing}")
        print(f"Skipped (bad row):  {len(skipped_bad_rows)}")

        if skipped_bad_rows:
            print("\nBad rows, first 10:")
            for line_number, reason in skipped_bad_rows[:10]:
                print(f"  line {line_number}: {reason}")

        if not to_insert and skipped_existing == len(rows):
            print("\nAll records already exist, nothing to do.")


if __name__ == "__main__":
    seed_records()
