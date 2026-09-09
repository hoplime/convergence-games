# pyright: reportImportCycles=false
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

from advanced_alchemy.types import DateTimeUTC
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._game_requirement import GameRequirement
    from ._game_requirement_time_slot_link import GameRequirementTimeSlotLink
    from ._room import Room
    from ._session import Session
    from ._table import Table
    from ._time_slot import TimeSlot
    from ._user_event_compensation_transaction import UserEventCompensationTransaction
    from ._user_event_d20_transaction import UserEventD20Transaction
    from ._user_event_role import UserEventRole


class Event(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    start_date: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True), index=True)
    end_date: Mapped[dt.datetime] = mapped_column(DateTimeUTC(timezone=True), index=True)
    timezone: Mapped[str] = mapped_column(default="Pacific/Auckland")
    max_party_size: Mapped[int] = mapped_column(default=3, server_default="3")

    # Time span gating — NULL = default (submissions/editing open; preferences/planner closed)
    submissions_open_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    submissions_close_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    editing_close_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    preferences_open_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)
    planner_open_at: Mapped[dt.datetime | None] = mapped_column(DateTimeUTC(timezone=True), nullable=True)

    def is_submissions_open(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        if self.submissions_open_at is not None and now < self.submissions_open_at:
            return False
        if self.submissions_close_at is not None and now >= self.submissions_close_at:
            return False
        return True

    def is_editing_open(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        if self.submissions_open_at is not None and now < self.submissions_open_at:
            return False
        if self.editing_close_at is not None and now >= self.editing_close_at:
            return False
        return True

    def is_preferences_open(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        if self.preferences_open_at is None or now < self.preferences_open_at:
            return False
        return True

    def is_planner_open(self, now: dt.datetime | None = None) -> bool:
        now = now or dt.datetime.now(dt.UTC)
        if self.planner_open_at is None or now < self.planner_open_at:
            return False
        return True

    # Relationships
    rooms: Mapped[list[Room]] = relationship(back_populates="event", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="event", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="event", lazy="noload", cascade="all, delete-orphan")
    time_slots: Mapped[list[TimeSlot]] = relationship(back_populates="event", lazy="noload", order_by="TimeSlot.id")
    games: Mapped[list[Game]] = relationship(back_populates="event", lazy="noload")
    user_roles: Mapped[list[UserEventRole]] = relationship(back_populates="event", lazy="noload")
    game_requirements: Mapped[list[GameRequirement]] = relationship(back_populates="event", lazy="noload")
    game_requirement_time_slot_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="event", lazy="noload"
    )
    d20_transactions: Mapped[list[UserEventD20Transaction]] = relationship(back_populates="event", lazy="noload")
    compensation_transactions: Mapped[list[UserEventCompensationTransaction]] = relationship(
        back_populates="event", lazy="noload"
    )
