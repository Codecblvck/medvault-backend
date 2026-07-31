"""add patient hospital id sequence

Revision ID: 883cc3f1332e
Revises: d0f40954c609
Create Date: 2026-07-30 12:48:42.913742

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '883cc3f1332e'
down_revision = 'd0f40954c609'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE SEQUENCE IF NOT EXISTS patient_hospital_id_seq START 1")


def downgrade():
    op.execute("DROP SEQUENCE IF EXISTS patient_hospital_id_seq")
