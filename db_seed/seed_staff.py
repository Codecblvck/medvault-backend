"""
Seeds the synthetic staff dataset (seeds/medvault_synthetic_staff_50.csv)
into the database.

Idempotent by design: email is the natural unique key (DB-enforced), so
rerunning this script only has to check that one column to know what
already exists.

Depends on seed_roles.py having already been run, role_id is looked up by
name, not created here. Depends on nothing else, patients and records don't
need to exist for staff to be seeded.

The CSV has no password column at all, every seeded staff account shares
one fixed, obviously-fake password, hashed once with bcrypt. This is a
dev/demo-only credential for populating the database with a realistic
volume of accounts, never meant to resemble a real, production credential.
Change it immediately if this script is ever pointed at anything other
than a local or demo database.

Run this once from the project root, python db_seed/seed_staff.py
Safe to run more than once.
"""

import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlalchemy as sa

from app import create_app
from app import system as core
from app.extensions import db, bcrypt
from app.auth.models import User

CSV_PATH = PROJECT_ROOT / "seeds" / "medvault_synthetic_staff_50.csv"

SEED_PASSWORD = "MedVaultSeed2026!"  # dev/demo-only, see module docstring

REQUIRED_COLUMNS = {
    "first_name", "last_name", "email", "role", "department",
    "phone", "status", "license_reference",
}

# CSV role labels -> RoleName enum values. Confirmed 1:1 against
# app/system/access.py, no ambiguity, unrecognized values are skipped
# and reported rather than guessed at.
ROLE_TRANSLATION = {
    "Administrator": core.RoleName.admin,
    "Doctor": core.RoleName.doctor,
    "Nurse": core.RoleName.nurse,
    "Laboratory Technician": core.RoleName.lab_technician,
    "Records Officer": core.RoleName.records_officer,
    "Auditor": core.RoleName.auditor,
}

# CSV status labels -> (is_active, is_locked). "On Leave" maps to a still
# valid, still active account, confirmed deliberately, since there is no
# leave-of-absence concept anywhere in the schema, distinct from a
# deactivated or locked account.
STATUS_TRANSLATION = {
    "Active": (True, False),
    "On Leave": (True, False),
}


def parse_row(row, role_id_by_name):
    """
    Builds a User instance from one CSV row. Raises ValueError with a clear
    message on anything malformed or unrecognized, so the caller can skip
    just this row rather than the whole run.
    """
    email = row["email"].strip().lower()
    if not email:
        raise ValueError("email is blank")

    role_label = row["role"].strip()
    role_name = ROLE_TRANSLATION.get(role_label)
    if role_name is None:
        raise ValueError(f"role '{role_label}' has no known translation")

    role_id = role_id_by_name.get(role_name)
    if role_id is None:
        raise ValueError(
            f"role '{role_name.value}' not found in roles table, "
            f"run seed_roles.py first"
        )

    status_label = row["status"].strip()
    status_pair = STATUS_TRANSLATION.get(status_label)
    if status_pair is None:
        raise ValueError(f"status '{status_label}' has no known translation")
    is_active, is_locked = status_pair

    user = User()
    user.first_name = row["first_name"].strip()
    user.last_name = row["last_name"].strip()
    user.email = email
    user.password_hash = bcrypt.generate_password_hash(SEED_PASSWORD).decode("utf-8")
    user.role_id = role_id
    user.department = row["department"].strip() or None
    user.phone = row["phone"].strip() or None
    user.license_number = row["license_reference"].strip() or None
    user.is_active = is_active
    user.is_locked = is_locked

    return user


def seed_staff():
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

        role_id_by_name = {
            role.role_name: role.id
            for role in db.session.scalars(sa.select(core.Role))
        }
        if not role_id_by_name:
            print("No roles found in the roles table. Run seed_roles.py first.")
            return

        existing_emails = set(
            db.session.scalars(sa.select(User.email))
        )

        to_insert = []
        skipped_existing = 0
        skipped_bad_rows = []
        seen_in_this_run = set()

        for line_number, row in enumerate(rows, start=2):  # header is line 1
            email = row.get("email", "").strip().lower()

            if email in existing_emails or email in seen_in_this_run:
                skipped_existing += 1
                continue

            try:
                user = parse_row(row, role_id_by_name)
            except ValueError as e:
                skipped_bad_rows.append((line_number, str(e)))
                continue

            to_insert.append(user)
            seen_in_this_run.add(email)

        if to_insert:
            db.session.add_all(to_insert)
            db.session.commit()

        print(f"Rows in CSV:        {len(rows)}")
        print(f"Inserted:           {len(to_insert)}")
        print(f"Skipped (existing): {skipped_existing}")
        print(f"Skipped (bad row):  {len(skipped_bad_rows)}")

        if to_insert:
            print(f"\nSeeded password for all new accounts: {SEED_PASSWORD}")
            print("Dev/demo-only, do not use this on any real deployment.")

        if skipped_bad_rows:
            print("\nBad rows, first 10:")
            for line_number, reason in skipped_bad_rows[:10]:
                print(f"  line {line_number}: {reason}")

        if not to_insert and skipped_existing == len(rows):
            print("\nAll staff already exist, nothing to do.")


if __name__ == "__main__":
    seed_staff()
