from __future__ import annotations

import datetime as dt
from typing import Any

from advanced_alchemy.base import BigIntAuditBase
from sqlalchemy import Connection, Enum, ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy import event as sqla_event
from sqlalchemy.orm import Mapped, Mapper, mapped_column, relationship
from sqlalchemy.orm import Session as DBSession

from convergence_games.app.context import user_id_ctx
from convergence_games.db.enums import (
    GameCrunch,
    GameNarrativism,
    GameTone,
    LoginProvider,
    Role,
)


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


# Game Information Models
class Event(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")
    start_date: Mapped[dt.datetime] = mapped_column(index=True)
    end_date: Mapped[dt.datetime] = mapped_column(index=True)

    # Relationships
    rooms: Mapped[list[Room]] = relationship(back_populates="event", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="event", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(back_populates="event", lazy="noload")
    event_statuses: Mapped[list[UserEventStatus]] = relationship(back_populates="event", lazy="noload")
    time_slots: Mapped[list[TimeSlot]] = relationship(back_populates="event", lazy="noload")
    games: Mapped[list[Game]] = relationship(back_populates="event", lazy="noload")
    user_roles: Mapped[list[UserEventRole]] = relationship(back_populates="event", lazy="noload")


class System(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")

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

    # Assocation Proxy Relationships
    genre_links: Mapped[list[GameGenreLink]] = relationship(back_populates="game", lazy="noload")
    content_warning_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="game", lazy="noload")

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

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


class Room(Base):
    name: Mapped[str]
    description: Mapped[str]

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="rooms", lazy="noload")
    tables: Mapped[list[Table]] = relationship(back_populates="room", lazy="noload")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


class Table(Base):
    name: Mapped[str]

    # Foreign Keys
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    room: Mapped[Room] = relationship(back_populates="tables", lazy="noload")
    event: Mapped[Event] = relationship(back_populates="tables", lazy="noload")
    sessions: Mapped[list[Session]] = relationship(
        back_populates="table", foreign_keys="Session.table_id", lazy="noload"
    )

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


@sqla_event.listens_for(Table, "before_insert")
def table_before_insert(mapper: Mapper, connection: Connection, target: Table):
    if target.event_id is None:
        target.event_id = target.room.event_id


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
    table: Mapped[Table] = relationship(back_populates="sessions", foreign_keys=table_id, lazy="noload")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="sessions", foreign_keys=time_slot_id, lazy="noload")
    event: Mapped[Event] = relationship(back_populates="sessions", lazy="noload")

    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # https://stackoverflow.com/a/63922398
        # These constraints ensure that the Game, Table and TimeSlot are part of the same Event
        ForeignKeyConstraint(
            ["game_id", "event_id"],
            ["game.id", "game.event_id"],
            name="fk_session_game_id_event_id_game",
        ),
        ForeignKeyConstraint(
            ["table_id", "event_id"],
            ["table.id", "table.event_id"],
            name="fk_session_table_id_event_id_table",
        ),
        ForeignKeyConstraint(
            ["time_slot_id", "event_id"],
            ["time_slot.id", "time_slot.event_id"],
            name="fk_session_time_slot_id_event_id_time_slot",
        ),
    )


# User Information Models
class User(Base):
    name: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str] = mapped_column(default="")

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="gamemaster", primaryjoin="User.id == Game.gamemaster_id", lazy="noload"
    )
    event_statuses: Mapped[list[UserEventStatus]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventStatus.user_id", lazy="noload"
    )
    logins: Mapped[list[UserLogin]] = relationship(
        back_populates="user", primaryjoin="User.id == UserLogin.user_id", lazy="noload"
    )
    event_roles: Mapped[list[UserEventRole]] = relationship(
        back_populates="user", primaryjoin="User.id == UserEventRole.user_id", lazy="noload"
    )


class UserEventStatus(Base):
    golden_d20s: Mapped[int] = mapped_column(default=0)
    compensation: Mapped[int] = mapped_column(default=0)

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="event_statuses", lazy="noload")
    user: Mapped[User] = relationship(back_populates="event_statuses", foreign_keys=user_id, lazy="noload")


class UserEventRole(Base):
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)

    # Foreign Keys
    event_id: Mapped[int | None] = mapped_column(ForeignKey("event.id"), index=True, nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="user_roles", lazy="noload")
    user: Mapped[User] = relationship(
        back_populates="event_roles", primaryjoin="User.id == UserEventRole.user_id", lazy="noload"
    )

    __table_args__ = (UniqueConstraint("event_id", "user_id", "role"),)


class UserLogin(Base):
    provider: Mapped[LoginProvider] = mapped_column(Enum(LoginProvider, validate_strings=True), index=True)
    provider_user_id: Mapped[str] = mapped_column(index=True)

    # Foreign Keys
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    user: Mapped[User] = relationship(back_populates="logins", foreign_keys=user_id, lazy="noload")

    __table_args__ = (UniqueConstraint("provider", "provider_user_id"), UniqueConstraint("user_id", "provider"))
