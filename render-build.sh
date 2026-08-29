#!/usr/bin/env bash
# Render build command. Runs on every deploy, so every step below must be
# safe to run more than once, migrations are idempotent by nature, and every
# script under db_seed/ is written to skip rows that already exist rather
# than duplicating them.
#
# `set -e` means the whole build stops at the first failing step, a failed
# migration or a broken seed script should never be silently skipped in
# favor of continuing on to the next one.
set -e

echo "Installing dependencies..."
#pip install -r requirements.txt

echo "Running database migrations..."
#flask db upgrade

echo "Seeding roles..."
python db_seed/seed_roles.py

echo "Seeding admin account..."
python db_seed/seed_admin.py

echo "Seeding patients..."
python db_seed/seed_patients.py

# Appended here as they're built, each one strictly after the step it
# depends on:
echo "Seeding staffs..."
python db_seed/seed_staff.py     

echo "Assigning doctors to patients..."
python db_seed/assign_doctors.py     

echo "Seeding records..."
python db_seed/seed_records.py       

echo "Build complete."
