import datetime as dt

from sqlalchemy import UniqueConstraint
from sqlmodel import Enum, Field, Relationship, SQLModel

from convergence_games.db.extra_types import GameCrunch, GameNarrativism, GameTone


# region Links
class GameGenreLink(SQLModel, table=True):
    game_id: int | None = Field(default=None, foreign_key="game.id", primary_key=True)
    genre_id: int | None = Field(default=None, foreign_key="genre.id", primary_key=True)


# endregion


# region System
class SystemBase(SQLModel):
    name: str = Field(index=True, unique=True)


class System(SystemBase, table=True):
    id: int | None = Field(default=None, primary_key=True)
    games: list["Game"] = Relationship(back_populates="system")


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


# endregion


# regoion Game
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

    gamemaster_id: int = Field(foreign_key="person.id")
    system_id: int = Field(foreign_key="system.id")


class Game(GameBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    genres: list[Genre] = Relationship(back_populates="games", link_model=GameGenreLink)
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


# endregion


# region Person
class PersonBase(SQLModel):
    name: str = Field(index=True)
    email: str = Field(index=True)


class Person(PersonBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    gmd_games: list[Game] = Relationship(back_populates="gamemaster")


# endregion


# region TimeSlot
class TimeSlotBase(SQLModel):
    start_time: dt.datetime
    end_time: dt.datetime


class TimeSlot(TimeSlotBase, table=True):
    id: int | None = Field(default=None, primary_key=True)

    table_allocations: list["TableAllocation"] = Relationship(back_populates="slot")


# endregion


# region TableAllocation
class TableAllocationBase(SQLModel):
    table_number: int = Field(index=True)
    slot_id: int = Field(foreign_key="timeslot.id")
    game_id: int = Field(foreign_key="game.id")


class TableAllocation(TableAllocationBase, table=True):
    id: int = Field(primary_key=True)

    slot: TimeSlot = Relationship(back_populates="table_allocations")
    game: Game = Relationship(back_populates="table_allocations")
    __table_args__ = (UniqueConstraint("table_number", "slot_id", name="unique_table_allocation"),)


# endregion
