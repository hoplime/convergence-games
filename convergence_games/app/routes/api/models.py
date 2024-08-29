from dataclasses import dataclass

from sqlmodel import SQLModel

from convergence_games.db.models import (
    Game,
    GameCreate,
    GameRead,
    GameUpdate,
    GameWithExtra,
    Genre,
    GenreCreate,
    GenreRead,
    GenreUpdate,
    GenreWithExtra,
    Person,
    PersonCreate,
    PersonRead,
    PersonUpdate,
    PersonWithExtra,
    SessionPreference,
    SessionPreferenceCreate,
    SessionPreferenceRead,
    SessionPreferenceUpdate,
    SessionPreferenceWithExtra,
    System,
    SystemCreate,
    SystemRead,
    SystemUpdate,
    SystemWithExtra,
    Table,
    TableAllocation,
    TableAllocationCreate,
    TableAllocationRead,
    TableAllocationUpdate,
    TableAllocationWithExtra,
    TableCreate,
    TableRead,
    TableUpdate,
    TableWithExtra,
    TimeSlot,
    TimeSlotCreate,
    TimeSlotRead,
    TimeSlotUpdate,
    TimeSlotWithExtra,
)


@dataclass
class ModelBoilerplate:
    table: type[SQLModel]
    create: type[SQLModel] | None = None
    read: type[SQLModel] | None = None
    extra: type[SQLModel] | None = None
    update: type[SQLModel] | None = None


GAME = ModelBoilerplate(
    table=Game,
    create=GameCreate,
    read=GameRead,
    extra=GameWithExtra,
    update=GameUpdate,
)

GENRE = ModelBoilerplate(
    table=Genre,
    create=GenreCreate,
    read=GenreRead,
    extra=GenreWithExtra,
    update=GenreUpdate,
)


PERSON = ModelBoilerplate(
    table=Person,
    create=PersonCreate,
    read=PersonRead,
    extra=PersonWithExtra,
    update=PersonUpdate,
)

SESSION_PREFERENCE = ModelBoilerplate(
    table=SessionPreference,
    create=SessionPreferenceCreate,
    read=SessionPreferenceRead,
    extra=SessionPreferenceWithExtra,
    update=SessionPreferenceUpdate,
)

SYSTEM = ModelBoilerplate(
    table=System,
    create=SystemCreate,
    read=SystemRead,
    extra=SystemWithExtra,
    update=SystemUpdate,
)

TABLE = ModelBoilerplate(
    table=Table,
    create=TableCreate,
    read=TableRead,
    extra=TableWithExtra,
    update=TableUpdate,
)

TABLE_ALLOCATION = ModelBoilerplate(
    table=TableAllocation,
    create=TableAllocationCreate,
    read=TableAllocationRead,
    extra=TableAllocationWithExtra,
    update=TableAllocationUpdate,
)

TIMESLOT = ModelBoilerplate(
    table=TimeSlot,
    create=TimeSlotCreate,
    read=TimeSlotRead,
    extra=TimeSlotWithExtra,
    update=TimeSlotUpdate,
)

boilerplates = [
    GAME,
    GENRE,
    PERSON,
    SESSION_PREFERENCE,
    SYSTEM,
    TABLE,
    TIMESLOT,
    TABLE_ALLOCATION,
]
