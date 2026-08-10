from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import Connection, ForeignKey, Integer, UniqueConstraint
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship

from convergence_games.db.enums import (
    GameActivityRequirement,
    GameEquipmentRequirement,
    GameRoomRequirement,
    GameTableSizeRequirement,
)

from ._base import Base, foreign_key_constraint_with_event

if TYPE_CHECKING:
    from ._event import Event
    from ._game import Game
    from ._game_requirement_time_slot_link import GameRequirementTimeSlotLink
    from ._time_slot import TimeSlot


class GameRequirement(Base):
    times_to_run: Mapped[int] = mapped_column(default=1)
    scheduling_notes: Mapped[str] = mapped_column(default="")
    table_size_requirement: Mapped[GameTableSizeRequirement] = mapped_column(
        Integer, default=GameTableSizeRequirement.NONE
    )
    table_size_notes: Mapped[str] = mapped_column(default="")
    equipment_requirement: Mapped[GameEquipmentRequirement] = mapped_column(
        Integer, default=GameEquipmentRequirement.NONE
    )
    equipment_notes: Mapped[str] = mapped_column(default="")
    activity_requirement: Mapped[GameActivityRequirement] = mapped_column(Integer, default=GameActivityRequirement.NONE)
    activity_notes: Mapped[str] = mapped_column(default="")
    room_requirement: Mapped[GameRoomRequirement] = mapped_column(Integer, default=GameRoomRequirement.NONE)
    room_notes: Mapped[str] = mapped_column(default="")

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(
        back_populates="game_requirement", foreign_keys=game_id, single_parent=True, lazy="noload"
    )
    event: Mapped[Event] = relationship(back_populates="game_requirements", foreign_keys=event_id, lazy="noload")
    available_time_slots: Mapped[list[TimeSlot]] = relationship(
        back_populates="game_requirements",
        secondary="game_requirement_time_slot_link",
        primaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        secondaryjoin="TimeSlot.id == GameRequirementTimeSlotLink.time_slot_id",
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    time_slot_links: Mapped[list[GameRequirementTimeSlotLink]] = relationship(
        back_populates="game_requirement",
        primaryjoin="GameRequirement.id == GameRequirementTimeSlotLink.game_requirement_id",
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint("game_id"),
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
        foreign_key_constraint_with_event("game_requirement", "game"),
    )


@sqla_event.listens_for(GameRequirement, "before_insert")
def game_requirement_before_insert(mapper: Mapper[Any], connection: Connection, target: GameRequirement):
    if target.event_id is None:
        target.event_id = target.game.event_id
