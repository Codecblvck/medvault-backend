import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from sqlalchemy import ForeignKey, String, func, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.extensions import db, jwt

if TYPE_CHECKING:
    from app.access_control.models import Role


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(255),unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(256), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id"), nullable=False
    )
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    patient_id = db.Column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=True, unique=True
    )
    phone: Mapped[str | None] = mapped_column(String(32))
    department: Mapped[str | None] = mapped_column(String(32))
    license_number: Mapped[str | None] = mapped_column(String(32))
    failed_login_count: Mapped[int] = mapped_column(default=0)
    is_locked: Mapped[bool] = mapped_column(default=False)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), onupdate=func.now()
    )

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def to_dict(self):
        """Serializes user columns to match production JSON requirements."""
        return {
            "id": self.id,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "role": (
                self.role.role_name.value
                if hasattr(self.role, "role_name")
                else str(self.role)
            ),
            "department": self.department if self.department else None,
            "is_active": bool(self.is_active),
            "is_locked": bool(self.is_locked),
            "created_at": (
                self.created_at.isoformat() + "Z"
                if isinstance(self.created_at, datetime)
                else None
            ),
        }


@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    user = User.query.filter_by(email=identity).first()

    if user is None or not user.is_active:
        return None

    return user
