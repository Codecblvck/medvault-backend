from typing import Text
import uuid
from datetime import datetime
from sqlalchemy import String, ForeignKey, func, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID
from app.extensions import db


class AuditLog(db.Model):
    __tablename__ = 'audit_logs'

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete="RESTRICT"), nullable=True
    )
    attempted_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role_at_time: Mapped[str | None] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    record_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("records.id"), nullable=True
    )
    details: Mapped[Text | None] = mapped_column(Text)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String)
    entry_hash: Mapped[str] = mapped_column()
    timestamp: Mapped[datetime] = mapped_column(server_default=func.now())


    user = relationship("User", foreign_keys=[user_id])
