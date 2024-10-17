from __future__ import annotations

import datetime as dt
from typing import TypeAlias

from sqlmodel import Field, ForeignKeyConstraint, Relationship, SQLModel, UniqueConstraint

from convergence_games.db.enums import GameCrunch, GameNarrativism, GameTone

# Types
MEDIA_LINK: TypeAlias = str


# Game Information Link Models
class GameGenreLink(SQLModel, table=True):
    __tablename__ = "game_genre_link"
    game_id: int | None = Field(default=None, foreign_key="game.id", primary_key=True)
    genre_id: int | None = Field(default=None, foreign_key="genre.id", primary_key=True)


class GameContentWarningLink(SQLModel, table=True):
    __tablename__ = "game_content_warning_link"
    game_id: int | None = Field(default=None, foreign_key="game.id", primary_key=True)
    content_warning_id: int | None = Field(default=None, foreign_key="content_warning.id", primary_key=True)


# Game Information Base Models
class VenueBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str
    address: str
    profile_picture: MEDIA_LINK | None = Field(default=None)


class Venue(VenueBase, table=True):
    __tablename__ = "venue"
    id: int | None = Field(default=None, primary_key=True)
    rooms: list[Room] = Relationship(back_populates="venue")
    events: list[Event] = Relationship(back_populates="venue")


class EventBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str
    start_date: dt.datetime
    end_date: dt.datetime
    profile_picture: MEDIA_LINK | None = Field(default=None)
    venue_id: int = Field(foreign_key="venue.id")


class Event(EventBase, table=True):
    __tablename__ = "event"
    id: int | None = Field(default=None, primary_key=True)
    venue: Venue = Relationship(back_populates="events")
    sessions: list[Session] = Relationship(back_populates="event")
    user_event_infos: list[UserEventInfo] = Relationship(back_populates="event")
    time_slots: list[TimeSlot] = Relationship(back_populates="event")


class SystemBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str
    profile_picture: MEDIA_LINK | None = Field(default=None)


class System(SystemBase, table=True):
    __tablename__ = "system"
    id: int | None = Field(default=None, primary_key=True)
    games: list[Game] = Relationship(back_populates="system")


class GenreBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str


class Genre(GenreBase, table=True):
    __tablename__ = "genre"
    id: int | None = Field(default=None, primary_key=True)
    games: list[Game] = Relationship(back_populates="genres")


class ContentWarningBase(SQLModel):
    name: str = Field(index=True, unique=True)
    description: str


class ContentWarning(ContentWarningBase, table=True):
    __tablename__ = "content_warning"
    id: int | None = Field(default=None, primary_key=True)
    games: list[Game] = Relationship(back_populates="content_warnings")


class ExtraGMBase(SQLModel):
    gamemaster_id: int = Field(foreign_key="user.id")
    game_id: int = Field(foreign_key="game.id")


class ExtraGM(ExtraGMBase, table=True):
    __tablename__ = "extra_gm"
    __table_args__ = (UniqueConstraint("gamemaster_id", "game_id"),)
    id: int | None = Field(default=None, primary_key=True)


class GameBase(SQLModel):
    name: str = Field(index=True, unique=True)
    tagline: str
    description: str
    min_age: int
    crunch: GameCrunch = Field(default=GameCrunch.MEDIUM, index=True)
    narrativism: GameNarrativism = Field(default=GameNarrativism.BALANCED, index=True)
    tone: GameTone = Field(default=GameTone.LIGHT_HEARTED, index=True)
    player_count_minimum: int
    player_count_optimal: int
    player_count_maximum: int
    nz_made: bool = Field(default=False)
    designer_run: bool = Field(default=False)
    profile_picture: MEDIA_LINK | None = Field(default=None)
    system_id: int = Field(foreign_key="system.id")
    gamemaster_id: int = Field(foreign_key="user.id")
    event_id: int = Field(foreign_key="event.id")


class Game(GameBase, table=True):
    __tablename__ = "game"
    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )
    id: int | None = Field(default=None, primary_key=True)
    system: System = Relationship(back_populates="games")
    gamemaster: User = Relationship(back_populates="games")
    event: Event = Relationship(back_populates="games")
    genres: list[Genre] = Relationship(back_populates="games")
    content_warnings: list[ContentWarning] = Relationship(back_populates="games")
    extra_gms: list[ExtraGM] = Relationship(back_populates="game")
    sessions: list[Session] = Relationship(back_populates="game")


# Timetable Information Base Models
class TimeSlotBase(SQLModel):
    name: str
    start_time: dt.datetime
    end_time: dt.datetime
    event_id: int = Field(foreign_key="event.id")


class TimeSlot(TimeSlotBase, table=True):
    __tablename__ = "time_slot"
    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )
    id: int | None = Field(default=None, primary_key=True)
    event: Event = Relationship(back_populates="time_slots")
    sessions: list[Session] = Relationship(back_populates="time_slot")


class RoomBase(SQLModel):
    name: str
    description: str
    venue_id: int = Field(foreign_key="venue.id")


class Room(RoomBase, table=True):
    __tablename__ = "room"
    id: int | None = Field(default=None, primary_key=True)
    venue: Venue = Relationship(back_populates="rooms")
    tables: list[Table] = Relationship(back_populates="room")


class TableBase(SQLModel):
    name: str
    room_id: int = Field(foreign_key="room.id")


class Table(TableBase, table=True):
    __tablename__ = "table"
    id: int | None = Field(default=None, primary_key=True)
    room: Room = Relationship(back_populates="tables")
    sessions: list[Session] = Relationship(back_populates="table")


class SessionBase(SQLModel):
    game_id: int = Field(foreign_key="game.id")
    table_id: int = Field(foreign_key="table.id")
    time_slot_id: int = Field(foreign_key="time_slot.id")
    event_id: int = Field(foreign_key="event.id")  # Logically redundant, but necessary for constraints


class Session(SessionBase, table=True):
    __tablename__ = "session"
    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # These two constraints ensure that the Game and Session are part of the same Event
        ForeignKeyConstraint(["game_id", "event_id"], ["game.id", "game.event_id"]),
        ForeignKeyConstraint(["time_slot_id", "event_id"], ["time_slot.id", "time_slot.event_id"]),
    )
    id: int | None = Field(default=None, primary_key=True)
    game: Game = Relationship(back_populates="sessions")
    table: Table = Relationship(back_populates="sessions")
    time_slot: TimeSlot = Relationship(back_populates="sessions")
    event: Event = Relationship(back_populates="sessions")


# User Information Base Models
class UserEventInfoBase(SQLModel):
    golden_d20s: int = 0
    compensation: int = 0
    event_id: int = Field(foreign_key="event.id")
    user_id: int = Field(foreign_key="user.id")


class UserEventInfo(UserEventInfoBase, table=True):
    __tablename__ = "user_event_info"
    id: int | None = Field(default=None, primary_key=True)
    event: Event = Relationship(back_populates="user_event_infos")
    user: User = Relationship(back_populates="user_event_infos")
    compensations: list[Compensation] = Relationship(back_populates="user_event_info")


class UserBase(SQLModel):
    name: str = Field(index=True)
    email: str = Field(index=True, unique=True)
    date_of_birth: dt.date
    description: str
    profile_picture: MEDIA_LINK | None = Field(default=None)


class User(UserBase, table=True):
    __tablename__ = "user"
    id: int | None = Field(default=None, primary_key=True)
    games: list[Game] = Relationship(back_populates="gamemaster")
    user_event_infos: list[UserEventInfo] = Relationship(back_populates="user")


# Player Game Selection Base Models
class GroupBase(SQLModel):
    join_code: str = Field(index=True)
    time_slot_id: int = Field(foreign_key="time_slot.id")
    checked_in: bool = False


class Group(GroupBase, table=True):
    __tablename__ = "group"
    id: int | None = Field(default=None, primary_key=True)
    time_slot: TimeSlot = Relationship(back_populates="groups")
    group_session_preferences: list[GroupSessionPreference] = Relationship(back_populates="group")


class GroupSessionPreferenceBase(SQLModel):
    group_id: int = Field(foreign_key="group.id")
    session_id: int = Field(foreign_key="session.id")
    preference: int


class GroupSessionPreference(GroupSessionPreferenceBase, table=True):
    __tablename__ = "group_session_preference"
    __table_args__ = (UniqueConstraint("group_id", "session_id"),)
    id: int | None = Field(default=None, primary_key=True)
    group: Group = Relationship(back_populates="group_session_preferences")
    session: Session = Relationship(back_populates="group_session_preferences")


# Allocation Base Models
class AllocationResultBase(SQLModel):
    session_id: int = Field(foreign_key="session.id")
    group_id: int = Field(foreign_key="group.id")
    committed: bool = False


class AllocationResult(AllocationResultBase, table=True):
    __tablename__ = "allocation_result"
    __table_args__ = (UniqueConstraint("session_id", "group_id"),)
    id: int | None = Field(default=None, primary_key=True)
    session: Session = Relationship(back_populates="allocation_results")
    group: Group = Relationship(back_populates="allocation_results")


class CompensationBase(SQLModel):
    user_event_info_id: int = Field(foreign_key="user_event_info.id")
    time_slot_id: int = Field(foreign_key="time_slot.id")
    compensation_delta: int = Field(default=0)
    golden_d20s_delta: int = Field(default=0)
    applied: bool = False
    reset: bool = False


class Compensation(CompensationBase, table=True):
    __tablename__ = "compensation"
    __table_args__ = (UniqueConstraint("user_event_info_id", "time_slot_id"),)
    id: int | None = Field(default=None, primary_key=True)
    user_event_info: UserEventInfo = Relationship(back_populates="compensations")
    time_slot: TimeSlot = Relationship(back_populates="compensations")
