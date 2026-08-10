from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import UserGamePreferenceValue

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._time_slot import TimeSlot
    from ._user import User


class UserGamePreference(Base):
    preference: Mapped[UserGamePreferenceValue] = mapped_column(
        Enum(UserGamePreferenceValue, validate_strings=True), index=True, nullable=False
    )

    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    frozen_at_time_slot_id: Mapped[int | None] = mapped_column(
        ForeignKey("time_slot.id"), index=True, nullable=True, default=None
    )

    # Relationships
    game: Mapped[Game] = relationship(back_populates="user_preferences", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="all_game_preferences",
        primaryjoin="User.id == UserGamePreference.user_id",
        lazy="noload",
        viewonly=True,
    )
    frozen_at_time_slot: Mapped[TimeSlot | None] = relationship(
        back_populates="frozen_game_preferences",
        foreign_keys=frozen_at_time_slot_id,
        lazy="noload",
    )

    __table_args__ = (
        UniqueConstraint(
            "game_id",
            "user_id",
            "frozen_at_time_slot_id",
            postgresql_nulls_not_distinct=True,
        ),
    )
