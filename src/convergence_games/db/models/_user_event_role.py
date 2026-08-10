from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import Role

from ._base import Base

if TYPE_CHECKING:
    from ._event import Event
    from ._user import User


class UserEventRole(Base):
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)

    # Foreign Keys
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id"), index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="user_roles", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="event_roles", primaryjoin="User.id == UserEventRole.user_id", lazy="noload"
    )

    __table_args__ = (UniqueConstraint("event_id", "user_id", "role"),)
