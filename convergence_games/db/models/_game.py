# pyright: reportImportCycles=false
from __future__ import annotations

from typing import TYPE_CHECKING

# `and_` is not referenced directly below, but must be importable from this module's namespace:
# SQLAlchemy resolves the string-based primaryjoin="and_(...)" on Game.user_preferences (below) by
# evaluating it against this module's globals at mapper-configuration time.
from sqlalchemy import Enum, ForeignKey, Integer, UniqueConstraint, and_  # noqa: F401
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import (
    GameClassification,
    GameCoreActivity,
    GameCrunch,
    GameKSP,
    GameTone,
    SubmissionStatus,
)

from ._base import Base
from ._game_content_warning_link import GameContentWarningLink
from ._game_genre_link import GameGenreLink
from ._game_image_link import GameImageLink

if TYPE_CHECKING:
    from ._content_warning import ContentWarning
    from ._event import Event
    from ._game_requirement import GameRequirement
    from ._genre import Genre
    from ._image import Image
    from ._session import Session
    from ._system import System
    from ._user import User
    from ._user_game_played import UserGamePlayed
    from ._user_game_preference import UserGamePreference


class Game(Base):
    # Description Fields
    name: Mapped[str] = mapped_column(index=True)
    tagline: Mapped[str] = mapped_column(default="")
    description: Mapped[str] = mapped_column(default="")  # TODO: JSON type?

    # Tags
    classification: Mapped[GameClassification] = mapped_column(
        Enum(GameClassification), default=GameClassification.PG, index=True
    )
    crunch: Mapped[GameCrunch] = mapped_column(Enum(GameCrunch), default=GameCrunch.MEDIUM, index=True)
    core_activity: Mapped[GameCoreActivity] = mapped_column(Integer, default=GameCoreActivity.NONE, index=True)
    tone: Mapped[GameTone] = mapped_column(Enum(GameTone), default=GameTone.LIGHT_HEARTED, index=True)

    # Player Count
    player_count_minimum: Mapped[int] = mapped_column()
    player_count_optimum: Mapped[int] = mapped_column()
    player_count_maximum: Mapped[int] = mapped_column()

    # Bonus
    ksps: Mapped[GameKSP] = mapped_column(Integer, default=GameKSP.NONE)
    submission_status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.SUBMITTED, index=True
    )

    # Foreign Keys
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="games", lazy="noload")
    gamemaster: Mapped[User] = relationship(back_populates="games", foreign_keys=gamemaster_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="games", lazy="noload")
    game_requirement: Mapped[GameRequirement] = relationship(
        back_populates="game", foreign_keys="GameRequirement.game_id", lazy="noload"
    )
    sessions: Mapped[list[Session]] = relationship(back_populates="game", foreign_keys="Session.game_id", lazy="noload")
    genres: Mapped[list[Genre]] = relationship(
        back_populates="games",
        secondary=GameGenreLink.__table__,
        viewonly=True,
        lazy="noload",
    )
    content_warnings: Mapped[list[ContentWarning]] = relationship(
        back_populates="games",
        secondary=GameContentWarningLink.__table__,
        viewonly=True,
        lazy="noload",
    )
    images: Mapped[list[Image]] = relationship(
        back_populates="games",
        secondary=GameImageLink.__table__,
        viewonly=True,
        lazy="noload",
        order_by=GameImageLink.sort_order,
    )
    user_preferences: Mapped[list[UserGamePreference]] = relationship(
        back_populates="game",
        lazy="noload",
        primaryjoin="and_(Game.id == UserGamePreference.game_id, UserGamePreference.frozen_at_time_slot_id.is_(None))",
    )
    players: Mapped[list[UserGamePlayed]] = relationship(
        back_populates="game",
        primaryjoin="Game.id == UserGamePlayed.game_id",
        lazy="noload",
    )

    # Association Proxy Relationships
    genre_links: Mapped[list[GameGenreLink]] = relationship(back_populates="game", lazy="noload")
    content_warning_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="game", lazy="noload")
    image_links: Mapped[list[GameImageLink]] = relationship(back_populates="game", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )
