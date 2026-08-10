from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from advanced_alchemy.types import DateTimeUTC
from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import TimeSlotStatus

from ._base import Base
from ._game_requirement_time_slot_link import GameRequirementTimeSlotLink

if TYPE_CHECKING:
    from ._event import Event
    from ._game_requirement import GameRequirement
    from ._party import Party
    from ._session import Session
    from ._user_checkin_status import UserCheckinStatus
    from ._user_event_compensation_transaction import UserEventCompensationTransaction
    from ._user_event_d20_transaction import UserEventD20Transaction
    from ._user_game_preference import UserGamePreference


class TimeSlot(Base):
    name: Mapped[str] = mapped_column(default="")
    start_time: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    end_time: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True))
    checkin_open_time: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    status: Mapped[TimeSlotStatus] = mapped_column(
        Enum(TimeSlotStatus), default=TimeSlotStatus.PRE_ALLOCATION, server_default="PRE_ALLOCATION"
    )

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="time_slots", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="time_slot", foreign_keys="Session.time_slot_id", lazy="noload"
    )
    game_requirements: Mapped[list[GameRequirement]] = relationship(
        back_populates="available_time_slots",
        secondary=GameRequirementTimeSlotLink.__table__,
        primaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        secondaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        viewonly=True,
        lazy="noload",
    )
    parties: Mapped[list[Party]] = relationship(
        back_populates="time_slot", foreign_keys="Party.time_slot_id", lazy="noload"
    )
    d20_transactions: Mapped[list[UserEventD20Transaction]] = relationship(
        back_populates="associated_time_slot",
        foreign_keys="UserEventD20Transaction.associated_time_slot_id",
        lazy="noload",
    )
    compensation_transactions: Mapped[list[UserEventCompensationTransaction]] = relationship(
        back_populates="associated_time_slot",
        foreign_keys="UserEventCompensationTransaction.associated_time_slot_id",
        lazy="noload",
    )
    checkin_statuses: Mapped[list[UserCheckinStatus]] = relationship(back_populates="time_slot", lazy="noload")
    frozen_game_preferences: Mapped[list[UserGamePreference]] = relationship(
        back_populates="frozen_at_time_slot", lazy="noload"
    )

    # Association Proxy Relationships
    game_requirement_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="time_slot",
        primaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        lazy="noload",
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )

    @property
    def duration(self) -> dt.timedelta:
        return self.end_time - self.start_time
