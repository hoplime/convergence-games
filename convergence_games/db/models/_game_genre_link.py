from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._genre import Genre


class GameGenreLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genre.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="genre_links", lazy="noload")
    genre: Mapped[Genre] = relationship(back_populates="game_links", lazy="noload")

    __table_args__ = (UniqueConstraint("game_id", "genre_id"),)
