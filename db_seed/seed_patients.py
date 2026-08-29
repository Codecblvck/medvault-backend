"""
Seeds the synthetic patient dataset (seeds/medvault_synthetic_patients_500-1.csv)
into the database.

Idempotent by design: hospital_id is taken directly from the CSV's
hospital_id_reference column (e.g. MV-00001), never from the live
nextval('patient_hospital_id_seq') sequence used by POST /patients. This
keeps seeded patients (MV- prefix) permanently distinguishable from real
patients created through the app (MR- prefix), and means rerunning this
script only has to check one column, hospital_id, to know what already
exists. Bad rows are skipped individually and reported, not fatal to the
whole run.

Run this once from the project root, python seed_patients.py
Safe to run more than once.
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# db_seed/ is one level below the project root, add the root to sys.path so
# `from app import ...` resolves no matter what directory this is run from.
sys.path.insert(0, str(PROJECT_ROOT))

import sqlalchemy as sa

from app import create_app
from app.extensions import db
from app.patients.models import Patient, PatientStatus

# seeds/ lives at the project root, not next to this script, so anchor off
# PROJECT_ROOT rather than this file's own parent.
CSV_PATH = PROJECT_ROOT / "seeds" / "medvault_synthetic_patients_500.csv"

REQUIRED_COLUMNS = {
    "first_name", "last_name", "age", "gender", "blood_group", "ward",
    "phone", "address", "national_id", "status", "hospital_id_reference",
}


def parse_row(row, line_number):
    """
    Builds a Patient instance from one CSV row. Raises ValueError with a
    clear message on anything malformed, so the caller can skip just this
    row rather than the whole run.
    """
    hospital_id = row["hospital_id_reference"].strip()
    if not hospital_id:
        raise ValueError("hospital_id_reference is blank")

    try:
        age = int(row["age"])
    except ValueError:
        raise ValueError(f"age '{row['age']}' is not a valid integer")

    try:
        status = PatientStatus(row["status"].strip())
    except ValueError:
        raise ValueError(
            f"status '{row['status']}' does not match any PatientStatus value"
        )

    patient = Patient()
    patient.first_name = row["first_name"].strip()
    patient.last_name = row["last_name"].strip()
    patient.age = age
    patient.gender = row["gender"].strip() or None
    patient.blood_group = row["blood_group"].strip() or None
    patient.ward = row["ward"].strip() or None
    patient.phone = row["phone"].strip() or None
    patient.address = row["address"].strip() or None
    patient.national_id = row["national_id"].strip() or None
    patient.status = status
    patient.hospital_id = hospital_id
    # assigned_doctor_id intentionally left null, staff does not exist yet.
    # A later pass (or the staff seed step) can backfill this.

    return patient


def seed_patients():
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

        # One query for every hospital_id already in the database, rather
        # than one query per row. This is the entire idempotency check.
        existing_ids = set(
            db.session.scalars(sa.select(Patient.hospital_id))
        )

        to_insert = []
        skipped_existing = 0
        skipped_bad_rows = []
        seen_in_this_run = set()

        for line_number, row in enumerate(rows, start=2):  # header is line 1
            hospital_id = row.get("hospital_id_reference", "").strip()

            if hospital_id in existing_ids or hospital_id in seen_in_this_run:
                skipped_existing += 1
                continue

            try:
                patient = parse_row(row, line_number)
            except ValueError as e:
                skipped_bad_rows.append((line_number, str(e)))
                continue

            to_insert.append(patient)
            seen_in_this_run.add(hospital_id)

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
            print("\nAll patients already exist, nothing to do.")


if __name__ == "__main__":
    seed_patients()
