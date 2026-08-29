"""
Backfills Patient.assigned_doctor_id for patients that don't have one yet.

Runs after both seed_patients.py and seed_staff.py, patients are seeded
with no doctor (staff didn't exist yet), doctors exist only once
seed_staff.py has run.

Idempotent by design: only touches patients where assigned_doctor_id IS
NULL, so a patient that already has a doctor is never reassigned, and
rerunning this script after it's already completed is a no-op.

Assignment is round-robin, doctors ordered by id, patients ordered by
hospital_id, so the result is deterministic and reproducible on rerun,
not randomly different each time. This spreads patients evenly across
however many doctors currently exist.

Run this once from the project root, python db_seed/assign_doctors.py
Safe to run more than once.
"""

import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import sqlalchemy as sa

from app import create_app
from app import system as core
from app.extensions import db
from app.auth.models import User
from app.patients.models import Patient


def assign_doctors():
    app = create_app()

    with app.app_context():
        doctors_stmt = (
            sa.select(User)
            .join(core.Role, User.role_id == core.Role.id)
            .where(core.Role.role_name == core.RoleName.doctor)
            .order_by(User.id)
        )
        doctors = list(db.session.scalars(doctors_stmt))

        if not doctors:
            print("No doctors found. Run seed_staff.py first.")
            return

        unassigned_stmt = (
            sa.select(Patient)
            .where(Patient.assigned_doctor_id.is_(None))
            .order_by(Patient.hospital_id)
        )
        unassigned_patients = list(db.session.scalars(unassigned_stmt))

        if not unassigned_patients:
            print("All patients already have a doctor assigned, nothing to do.")
            return

        doctor_count = len(doctors)
        assignment_counts = Counter()

        for index, patient in enumerate(unassigned_patients):
            doctor = doctors[index % doctor_count]
            patient.assigned_doctor_id = doctor.id
            assignment_counts[f"{doctor.first_name} {doctor.last_name}"] += 1

        db.session.commit()

        print(f"Doctors available:     {doctor_count}")
        print(f"Patients assigned:     {len(unassigned_patients)}")
        print("\nPatients per doctor:")
        for name, count in sorted(assignment_counts.items()):
            print(f"  {name}: {count}")


if __name__ == "__main__":
    assign_doctors()
