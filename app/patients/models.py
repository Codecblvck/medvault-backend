import uuid
import enum
from datetime import datetime

from sqlalchemy import String, UUID, ForeignKey, func, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ..extensions import db


class PatientStatus(enum.Enum):
    admitted = "Admitted"
    discharged = "Discharged"
    outpatient = "Outpatient"


class Patient(db.Model):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(5), nullable=True)
    ward: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    national_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )
    hospital_id: Mapped[str | None] = mapped_column(
        String(20), unique=True, nullable=True
    )
    assigned_doctor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[PatientStatus] = mapped_column(
        Enum(
            PatientStatus,
            values_callable=lambda x: [i.value for i in x],
            nullable=False,
            default=PatientStatus.outpatient,
        )
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    assigned_doctor = relationship("User", foreign_keys=[assigned_doctor_id])

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"
