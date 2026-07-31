import enum
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, Enum, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class RecordType(enum.Enum):
    lab_report = "Lab Report"
    imaging = "Imaging"
    prescription = "Prescription"
    discharge_summary = "Discharge Summary"
    vitals = "Vitals"
    clinical_notes = "Clinical Notes"


class Patient(db.Model):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    assigned_doctor = relationship("User", foreign_keys=[assigned_doctor_id])

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"


class Record(db.Model):
    __tablename__ = "records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False
    )
    uploaded_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    record_type: Mapped[RecordType] = mapped_column(
        Enum(RecordType, values_callable=lambda x: [i.value for i in x]),
        nullable=False
    )
    department: Mapped[str | None] = mapped_column(String(100))
    encrypted_data: Mapped[str] = mapped_column(Text, nullable=False)
    encrypted_aes_key: Mapped[str] = mapped_column(nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500))
    file_size: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    patient = relationship("Patient", foreign_keys=[patient_id])
    uploader = relationship("User", foreign_keys=[uploaded_by])
