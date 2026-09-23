from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.call import Call
    from app.models.call_participant import CallParticipant
    from app.models.contact import Contact
    from app.models.device import Device
    from app.models.preference import UserPreference
    from app.models.translation import TranslationSession


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (Index("ix_users_email", "email", unique=True),)

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    devices: Mapped[list["Device"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="owner", cascade="all, delete-orphan", foreign_keys="Contact.owner_id"
    )
    initiated_calls: Mapped[list["Call"]] = relationship(back_populates="initiator", cascade="all, delete-orphan")
    call_participations: Mapped[list["CallParticipant"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    translation_sessions: Mapped[list["TranslationSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    preference: Mapped["UserPreference | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
