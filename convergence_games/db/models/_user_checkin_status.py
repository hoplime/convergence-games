from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._time_slot import TimeSlot
    from ._user import User


class UserCheckinStatus(Base):
    checked_in: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), primary_key=True)

    # Relationships
    user: Mapped[User] = relationship(
        back_populates="checkin_statuses", primaryjoin="User.id == UserCheckinStatus.user_id", lazy="noload"
    )
    time_slot: Mapped[TimeSlot] = relationship(
        back_populates="checkin_statuses", foreign_keys=time_slot_id, lazy="noload"
    )

    __table_args__ = (UniqueConstraint("user_id", "time_slot_id"),)
