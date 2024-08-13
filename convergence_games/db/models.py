import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Enum, Field, Relationship, SQLModel

from convergence_games.db.extra_types import GameCrunch, GameNarrativism, GameTone


# region Links
class GameGenreLink(SQLModel, table=True):
    game_id: int | None = Field(default=None, foreign_key="game.id", primary_key=True)
    genre_id: int | None = Field(default=None, foreign_key="genre.id", primary_key=True)


class GameContentWarningLink(SQLModel, table=True):
    game_id: int | None = Field(default=None, foreign_key="game.id", primary_key=True)
    content_warning_id: int | None = Field(default=None, foreign_key="contentwarning.id", primary_key=True)


# endregion


# region System
class SystemBase(SQLModel):
    name: str = Field(index=True, unique=True)


class System(SystemBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    games: list["Game"] = Relationship(back_populates="system")


class SystemCreate(SystemBase):
    pass


class SystemRead(SystemBase):
    id: int
    test: str = "test"


class SystemWithExtra(SystemRead):
    games: list["Game"]


class SystemUpdate(SystemBase):
    name: str | None = None


# endregion


# region Genre
class GenreBase(SQLModel):
    name: str = Field(index=True, unique=True)


class Genre(GenreBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    games: list["Game"] = Relationship(back_populates="genres", link_model=GameGenreLink)


class GenreCreate(GenreBase):
    pass


class GenreRead(GenreBase):
    id: int


class GenreWithExtra(GenreRead):
    games: list["Game"]


class GenreUpdate(GenreBase):
    name: str | None = None


# endregion


# region ContentWarning
class ContentWarningBase(SQLModel):
    name: str = Field(index=True, unique=True)


class ContentWarning(ContentWarningBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    games: list["Game"] = Relationship(back_populates="content_warnings", link_model=GameContentWarningLink)


class ContentWarningCreate(ContentWarningBase):
    pass


class ContentWarningRead(ContentWarningBase):
    id: int


class ContentWarningWithExtra(ContentWarningRead):
    games: list["Game"]


class ContentWarningUpdate(ContentWarningBase):
    name: str | None = None


# endregion


# region Game
class GameBase(SQLModel):
    title: str = Field(index=True)
    description: str
    crunch: GameCrunch = Field(default=GameCrunch.MEDIUM, sa_type=Enum(GameCrunch), index=True)
    narrativism: GameNarrativism = Field(default=GameNarrativism.BALANCED, sa_type=Enum(GameNarrativism), index=True)
    tone: GameTone = Field(default=GameTone.LIGHT_HEARTED, sa_type=Enum(GameTone), index=True)
    age_suitability: str = Field(default="Anyone", index=True)
    minimum_players: int = Field(default=2)
    optimal_players: int = Field(default=4)
    maximum_players: int = Field(default=6)
    nz_made: bool = Field(default=False)
    designer_run: bool = Field(default=False)

    gamemaster_id: int = Field(foreign_key="person.id")
    system_id: int = Field(foreign_key="system.id")


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    genres: list[Genre] = Relationship(back_populates="games", link_model=GameGenreLink)
    content_warnings: list[ContentWarning] = Relationship(back_populates="games", link_model=GameContentWarningLink)
    gamemaster: "Person" = Relationship(back_populates="gmd_games")
    system: System = Relationship(back_populates="games")
    table_allocations: list["TableAllocation"] = Relationship(back_populates="game")

    def __str__(self):
        result = f"""
        ** {self.title} **
        {self.system.name} | {", ".join(genre.name for genre in self.genres)}
        {self.crunch} | {self.narrativism} | {self.tone} | {self.age_suitability} | {self.minimum_players} - {self.maximum_players} players
        {self.description}
        Run by: {self.gamemaster.name}
        """.strip()
        return "\n".join(line.lstrip() for line in result.split("\n"))


class GameCreate(GameBase):
    pass


class GameRead(GameBase):
    id: int


class GameUpdate(GameBase):
    title: str | None = None
    description: str | None = None
    crunch: GameCrunch | None = None
    narrativism: GameNarrativism | None = None
    tone: GameTone | None = None
    content_warnings: str | None = None
    age_suitability: str | None = None
    minimum_players: int | None = None
    optimal_players: int | None = None
    maximum_players: int | None = None
    gamemaster_id: int | None = None
    system_id: int | None = None
    nz_made: bool | None = None
    designer_run: bool | None = None


class GameWithExtra(GameRead):
    genres: list[Genre] = []
    content_warnings: list[ContentWarning] = []
    gamemaster: "Person"
    system: System
    table_allocations: list["TableAllocationWithSlot"] = []

    @property
    def schedule(self) -> list[tuple[str, list[bool]]]:
        # TODO: Assert that there are exactly 5 time slots, or be smart about time slots
        flags = [False] * 5
        for table_allocation in self.table_allocations:
            flags[table_allocation.time_slot_id - 1] = True
        result = [
            ("SAT", flags[:3]),
            ("SUN", flags[3:]),
        ]
        return result


# endregion


# region Person
class PersonBase(SQLModel):
    name: str = Field(index=True)
    email: str = Field(index=True)
    golden_d20s: int = Field(default=0)


class Person(PersonBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    gmd_games: list[Game] = Relationship(back_populates="gamemaster")
    session_preferences: list["SessionPreference"] = Relationship(back_populates="person")
    __table_args__ = (UniqueConstraint("email", name="unique_email"),)


class PersonCreate(PersonBase):
    pass


class PersonRead(PersonBase):
    id: int


class PersonWithExtra(PersonRead):
    gmd_games: list[Game]
    session_preferences: list["SessionPreference"]


class PersonUpdate(PersonBase):
    name: str | None = None
    email: str | None = None
    golden_d20s: int | None = None


# endregion


# region TimeSlot
class TimeSlotBase(SQLModel):
    name: str
    start_time: dt.datetime
    end_time: dt.datetime


class TimeSlot(TimeSlotBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    table_allocations: list["TableAllocation"] = Relationship(back_populates="time_slot")


class TimeSlotCreate(TimeSlotBase):
    pass


class TimeSlotRead(TimeSlotBase):
    id: int


class TimeSlotWithExtra(TimeSlotRead):
    table_allocations: list["TableAllocationWithExtra"]


class TimeSlotUpdate(TimeSlotBase):
    name: str | None = None
    start_time: dt.datetime | None = None
    end_time: dt.datetime | None = None


# endregion


# region TableAllocation
class TableAllocationBase(SQLModel):
    table_number: int = Field(index=True)
    time_slot_id: int = Field(foreign_key="timeslot.id")
    game_id: int = Field(foreign_key="game.id")


class TableAllocation(TableAllocationBase, table=True):
    id: int | None = Field(primary_key=True)

    time_slot: TimeSlot = Relationship(back_populates="table_allocations")
    game: Game = Relationship(back_populates="table_allocations")
    session_preferences: list["SessionPreference"] = Relationship(back_populates="table_allocation")
    __table_args__ = (UniqueConstraint("table_number", "time_slot_id", name="unique_table_allocation"),)


class TableAllocationCreate(TableAllocationBase):
    pass


class TableAllocationRead(TableAllocationBase):
    id: int


class TableAllocationWithExtra(TableAllocationRead):
    time_slot: TimeSlot
    game: GameWithExtra
    session_preferences: list["SessionPreference"]


class TableAllocationUpdate(TableAllocationBase):
    table_number: int | None = None
    slot_id: int | None = None
    game_id: int | None = None


class TableAllocationWithSlot(TableAllocationRead):
    time_slot: TimeSlot


# endregion


# region SessionPreference
class SessionPreferenceBase(SQLModel):
    preference: int = Field(default=3)
    person_id: int = Field(primary_key=True, foreign_key="person.id")
    table_allocation_id: int = Field(primary_key=True, foreign_key="tableallocation.id")


class SessionPreference(SessionPreferenceBase, table=True):
    person: Person = Relationship(back_populates="session_preferences")
    table_allocation: TableAllocation = Relationship(back_populates="session_preferences")


class SessionPreferenceCreate(SessionPreferenceBase):
    pass


class SessionPreferenceRead(SessionPreferenceBase):
    pass


class SessionPreferenceWithExtra(SessionPreferenceRead):
    person: Person
    table_allocation: TableAllocation


class SessionPreferenceUpdate(SessionPreferenceBase):
    weight: int | None = None
    person_id: int | None = None
    table_allocation_id: int | None = None


# endregion
