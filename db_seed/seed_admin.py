"""
One time setup script, seeds a single admin account directly into the database.
Run this once from the project root, python seed_admin.py
Safe to run more than once, exits early if an admin already exists.
"""

import sys
from pathlib import Path

# db_seed/ is one level below the project root, add the root to sys.path so
# `from app import ...` resolves no matter what directory this is run from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app import system as core
from app.extensions import db, bcrypt
from app.auth.models import User
import sqlalchemy as sa


def seed_admin():
    app = create_app()

    with app.app_context():
        # Check whether an admin already exists, avoid creating a duplicate
        existing_admin_stmt = (
            sa.select(User)
            .join(core.Role, User.role_id == core.Role.id)
            .filter(core.Role.role_name == "admin")
        )
        existing_admin = db.session.scalar(existing_admin_stmt)

        if existing_admin:
            print(f"Admin account already exists, email: {existing_admin.email}")
            return

        # Look up the admin role's id, never hardcode this number
        role_stmt = sa.select(core.Role).filter_by(role_name="admin")
        admin_role = db.session.scalar(role_stmt)

        if not admin_role:
            print("No admin role found in the roles table. Seed roles first.")
            return

        # Hash the password using the same method as the registration route
        password_hash = bcrypt.generate_password_hash("AdminPass123!").decode("utf-8")

        admin_user = User()
        admin_user.first_name="Rafael S."
        admin_user.last_name="Mozie"
        admin_user.email="admin@medvault.com"
        admin_user.password_hash=password_hash
        admin_user.role_id=admin_role.id

        db.session.add(admin_user)
        db.session.commit()

        print(
            f"Admin account created, email: {admin_user.email}, password: AdminPass123!"
        )


if __name__ == "__main__":
    seed_admin()
