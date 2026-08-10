from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import LoginProvider

from ._base import Base

if TYPE_CHECKING:
    from ._user import User


class UserLogin(Base):
    provider: Mapped[LoginProvider] = mapped_column(Enum(LoginProvider, validate_strings=True), index=True)
    provider_user_id: Mapped[str] = mapped_column(index=True)
    provider_email: Mapped[str | None] = mapped_column(index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="logins", foreign_keys=user_id, lazy="noload")

    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)
