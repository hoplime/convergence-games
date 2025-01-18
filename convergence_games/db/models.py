from __future__ import annotations

import datetime as dt
from typing import Any, TypeAlias

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import Enum, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session as DBSession

from convergence_games.app.context import user_id_ctx
from convergence_games.db.enums import GameCrunch, GameNarrativism, GameTone, LoginProvider, UserRole

# Types
MEDIA_LINK: TypeAlias = str


def get_object_session(obj) -> DBSession | None:
    return DBSession.object_session(obj)


def get_object_session_info(obj) -> dict[str, Any]:
    session = get_object_session(obj)
    if session is None:
        return {}
    return session.info


class UserAuditColumns:
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"),
        nullable=True,
        default=user_id_ctx.get,
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("user.id"),
        nullable=True,
        default=user_id_ctx.get,
        onupdate=user_id_ctx.get,
    )


class Base(BigIntAuditBase, UserAuditColumns):
    __abstract__ = True


# Game Information Link Models
class GameGenreLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genre.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="genre_links", lazy="noload")
    genre: Mapped[Genre] = relationship(back_populates="game_links", lazy="noload")


class GameContentWarningLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    content_warning_id: Mapped[int] = mapped_column(ForeignKey("content_warning.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="content_warning_links", lazy="noload")
    content_warning: Mapped[ContentWarning] = relationship(back_populates="game_links", lazy="noload")


class GameExtraGamemasterLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="extra_gamemaster_links", lazy="noload")
    gamemaster: Mapped[User] = relationship(
        back_populates="extra_game_links", foreign_keys=gamemaster_id, lazy="noload"
    )


# Game Information Models
class Venue(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]
    address: Mapped[str]
    # profile_picture: Mapped[MEDIA_LINK | None] = mapped_column(default=None, nullable=True)

    # Relationships
    rooms: Mapped[list[Room]] = relationship(back_populates="venue", lazy="noload")
    events: Mapped[list[Event]] = relationship(back_populates="venue", lazy="noload")


class Event(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    start_date: Mapped[dt.datetime] = mapped_column(index=True)
    end_date: Mapped[dt.datetime] = mapped_column(index=True)
    # profile_picture: Mapped[MEDIA_LINK | None] = mapped_column(default=None, nullable=True)

    # Foreign Keys
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), index=True)

    # Relationships
    venue: Mapped[Venue] = relationship(back_populates="events", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="event", lazy="noload")
    user_event_infos: Mapped[list[UserEventInfo]] = relationship(back_populates="event", lazy="noload")
    time_slots: Mapped[list[TimeSlot]] = relationship(back_populates="event", lazy="noload")
    games: Mapped[list[Game]] = relationship(back_populates="event", lazy="noload")


class System(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    # profile_picture: Mapped[MEDIA_LINK | None] = mapped_column(default=None, nullable=True)

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="system", lazy="noload")


class Genre(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="genres", secondary=GameGenreLink.__table__, viewonly=True, lazy="noload"
    )

    # Assocation Proxy Relationships
    game_links: Mapped[list[GameGenreLink]] = relationship(back_populates="genre", lazy="noload")


class ContentWarning(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="content_warnings", secondary=GameContentWarningLink.__table__, viewonly=True, lazy="noload"
    )

    # Assocation Proxy Relationships
    game_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="content_warning", lazy="noload")


class Game(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    tagline: Mapped[str]
    description: Mapped[str]
    min_age: Mapped[int]
    crunch: Mapped[GameCrunch] = mapped_column(Enum(GameCrunch), default=GameCrunch.MEDIUM, index=True)
    narrativism: Mapped[GameNarrativism] = mapped_column(
        Enum(GameNarrativism), default=GameNarrativism.BALANCED, index=True
    )
    tone: Mapped[GameTone] = mapped_column(Enum(GameTone), default=GameTone.LIGHT_HEARTED, index=True)
    player_count_minimum: Mapped[int]
    player_count_optimal: Mapped[int]
    player_count_maximum: Mapped[int]
    nz_made: Mapped[bool] = mapped_column(default=False)
    designer_run: Mapped[bool] = mapped_column(default=False)
    # profile_picture: Mapped[MEDIA_LINK | None] = mapped_column(default=None, nullable=True)

    # Foreign Keys
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="games", lazy="noload")
    gamemaster: Mapped[User] = relationship(back_populates="games", foreign_keys=gamemaster_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="games", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="game", foreign_keys="Session.game_id", lazy="noload")
    genres: Mapped[list[Genre]] = relationship(
        back_populates="games", secondary=GameGenreLink.__table__, viewonly=True, lazy="noload"
    )
    content_warnings: Mapped[list[ContentWarning]] = relationship(
        back_populates="games", secondary=GameContentWarningLink.__table__, viewonly=True, lazy="noload"
    )
    extra_gamemasters: Mapped[list[User]] = relationship(
        back_populates="extra_games",
        secondary=GameExtraGamemasterLink.__table__,
        viewonly=True,
        primaryjoin="Game.id == GameExtraGamemasterLink.game_id",
        secondaryjoin="GameExtraGamemasterLink.gamemaster_id == User.id",
        lazy="noload",
    )

    # Assocation Proxy Relationships
    genre_links: Mapped[list[GameGenreLink]] = relationship(back_populates="game", lazy="noload")
    content_warning_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="game", lazy="noload")
    extra_gamemaster_links: Mapped[list[GameExtraGamemasterLink]] = relationship(back_populates="game", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


# Timetable Information Models
class TimeSlot(Base):
    name: Mapped[str]
    start_time: Mapped[dt.datetime]
    end_time: Mapped[dt.datetime]

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="time_slots", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="time_slot", foreign_keys="Session.time_slot_id", lazy="noload"
    )
    groups: Mapped[list[Group]] = relationship(back_populates="time_slot", lazy="noload")
    compensations: Mapped[list[Compensation]] = relationship(back_populates="time_slot", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


class Room(Base):
    name: Mapped[str]
    description: Mapped[str]

    # Foreign Keys
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), index=True)

    # Relationships
    venue: Mapped[Venue] = relationship(back_populates="rooms", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="room", lazy="noload")


class Table(Base):
    name: Mapped[str]

    # Foreign Keys
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)

    # Relationships
    room: Mapped[Room] = relationship(back_populates="tables", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="table", lazy="noload")


class Session(Base):
    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("table.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(back_populates="sessions", foreign_keys=game_id, lazy="noload")
    table: Mapped[Table] = relationship(back_populates="sessions", lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="sessions", foreign_keys=time_slot_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="sessions", lazy="noload")
    group_session_preferences: Mapped[list[GroupSessionPreference]] = relationship(
        back_populates="session", lazy="noload"
    )
    allocation_results: Mapped[list[AllocationResult]] = relationship(back_populates="session", lazy="noload")

    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # These two constraints ensure that the Game and TimeSlot are part of the same Event
        ForeignKeyConstraint(
            ["game_id", "event_id"],
            ["game.id", "game.event_id"],
            name="fk_session_game_id_event_id_game",
        ),
        ForeignKeyConstraint(
            ["time_slot_id", "event_id"],
            ["time_slot.id", "time_slot.event_id"],
            name="fk_session_time_slot_id_event_id_time_slot",
        ),
    )


# User Information Models
class UserEventInfo(Base):
    golden_d20s: Mapped[int] = mapped_column(default=0)
    compensation: Mapped[int] = mapped_column(default=0)

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="user_event_infos", lazy="noload")
    user: Mapped[User] = relationship(back_populates="user_event_infos", foreign_keys=user_id, lazy="noload")
    compensations: Mapped[list[Compensation]] = relationship(back_populates="user_event_info", lazy="noload")


class User(Base):
    name: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(index=True, unique=True)
    # date_of_birth: Mapped[dt.date | None] = mapped_column(default=None, nullable=True)
    description: Mapped[str] = mapped_column(default="")
    # profile_picture: Mapped[MEDIA_LINK | None] = mapped_column(default=None)
    role: Mapped[UserRole] = mapped_column(default=UserRole.GUEST, index=True)

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="gamemaster", primaryjoin="User.id == Game.gamemaster_id", lazy="noload"
    )
    user_event_infos: Mapped[list[UserEventInfo]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventInfo.user_id", lazy="noload"
    )
    extra_games: Mapped[list[Game]] = relationship(
        back_populates="extra_gamemasters",
        secondary=GameExtraGamemasterLink.__table__,
        viewonly=True,
        primaryjoin="User.id == GameExtraGamemasterLink.gamemaster_id",
        secondaryjoin="GameExtraGamemasterLink.game_id == Game.id",
        lazy="noload",
    )
    logins: Mapped[list[UserLogin]] = relationship(
        back_populates="user", primaryjoin="User.id == UserLogin.user_id", lazy="noload"
    )

    # Assocation Proxy Relationships
    extra_game_links: Mapped[list[GameExtraGamemasterLink]] = relationship(
        back_populates="gamemaster", primaryjoin="User.id == GameExtraGamemasterLink.gamemaster_id", lazy="noload"
    )


class UserLogin(Base):
    provider: Mapped[LoginProvider] = mapped_column(Enum(LoginProvider, validate_strings=True), index=True)
    provider_user_id: Mapped[str] = mapped_column(index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="logins", foreign_keys=user_id, lazy="noload")

    __table_args__ = (UniqueConstraint("provider", "provider_user_id"), UniqueConstraint("user_id", "provider"))


# Player Game Selection Models
class Group(Base):
    join_code: Mapped[str] = mapped_column(index=True)
    checked_in: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)

    # Relationships
    time_slot: Mapped[TimeSlot] = relationship(back_populates="groups", lazy="noload")
    group_session_preferences: Mapped[list[GroupSessionPreference]] = relationship(
        back_populates="group", lazy="noload"
    )
    allocation_results: Mapped[list[AllocationResult]] = relationship(back_populates="group", lazy="noload")

    __table_args__ = (UniqueConstraint("time_slot_id", "join_code"),)


class GroupSessionPreference(Base):
    preference: Mapped[int]

    # Foreign Keys
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), index=True)

    # Relationships
    group: Mapped[Group] = relationship(back_populates="group_session_preferences", lazy="noload")
    session: Mapped[Session] = relationship(back_populates="group_session_preferences", lazy="noload")

    __table_args__ = (UniqueConstraint("group_id", "session_id"),)


# Allocation Base Models
class AllocationResult(Base):
    committed: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)

    # Relationships
    session: Mapped[Session] = relationship(back_populates="allocation_results", lazy="noload")
    group: Mapped[Group] = relationship(back_populates="allocation_results", lazy="noload")

    __table_args__ = (UniqueConstraint("session_id", "group_id"),)


class Compensation(Base):
    compensation_delta: Mapped[int] = mapped_column(default=0)
    golden_d20s_delta: Mapped[int] = mapped_column(default=0)
    applied: Mapped[bool] = mapped_column(default=False)
    reset: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    user_event_info_id: Mapped[int] = mapped_column(ForeignKey("user_event_info.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)

    # Relationships
    user_event_info: Mapped[UserEventInfo] = relationship(back_populates="compensations", lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="compensations", lazy="noload")

    __table_args__ = (UniqueConstraint("user_event_info_id", "time_slot_id"),)
