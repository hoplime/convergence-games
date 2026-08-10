from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy.orm import Mapped, mapped_column, relationship

from ._base import Base
from ._game_image_link import GameImageLink

if TYPE_CHECKING:
    from ._game import Game


class Image(Base):
    lookup_key: Mapped[UUID] = mapped_column(index=True, unique=True)

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="images",
        secondary=GameImageLink.__table__,
        viewonly=True,
        lazy="noload",
    )

    # Association Proxy Relationships
    game_links: Mapped[list[GameImageLink]] = relationship(back_populates="image", lazy="noload")
