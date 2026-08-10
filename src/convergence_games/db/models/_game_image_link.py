from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base

if TYPE_CHECKING:
    from ._game import Game
    from ._image import Image


class GameImageLink(Base):
    image_id: Mapped[int] = mapped_column(ForeignKey("image.id"), primary_key=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    sort_order: Mapped[int] = mapped_column(default=0)

    image: Mapped[Image] = relationship(back_populates="game_links", lazy="noload")
    game: Mapped[Game] = relationship(back_populates="image_links", lazy="noload")
