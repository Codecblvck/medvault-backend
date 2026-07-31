import enum
from typing import TYPE_CHECKING

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db

if TYPE_CHECKING:
    from app.auth.models import User


class RoleName(enum.Enum):
    admin = "admin"
    doctor = "doctor"
    nurse = "nurse"
    lab_technician = "lab_technician"
    records_officer = "records_officer"
    auditor = "auditor"
    patient = "patient"


class Role(db.Model):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    role_name: Mapped[RoleName] = mapped_column(
        Enum(RoleName, values_callable=lambda x: [i.value for i in x]),
        unique=True,
        nullable=False,
    )
    users: Mapped[list["User"]] = relationship("User", back_populates="role")
