from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._user import User


class UserGamePlayed(Base):
    allow_play_again: Mapped[bool] = mapped_column(default=False, server_default="0", index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)

    # Relationships
    user: Mapped[User] = relationship(
        back_populates="games_played", primaryjoin="User.id == UserGamePlayed.user_id", lazy="noload"
    )
    game: Mapped[Game] = relationship(
        back_populates="players", primaryjoin="Game.id == UserGamePlayed.game_id", lazy="noload"
    )

    __table_args__ = (UniqueConstraint("user_id", "game_id"),)
