from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Generator, TypeVar

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from convergence_games.db.base_data import ALL_BASE_DATA
from convergence_games.db.models import (
    Game,
    GameWithExtra,
    Genre,
    Person,
    System,
    TableAllocation,
    TableAllocationWithExtra,
    TimeSlot,
)
from convergence_games.db.sheets_importer import GoogleSheetsImporter
from convergence_games.settings import SETTINGS

engine: Engine | None = None


def get_session() -> Generator[Session, Any, None]:
    with Session(engine) as session:
        yield session


def get_engine() -> Engine:
    return engine


def create_db_and_tables(allow_recreate: bool = True) -> bool:
    global engine

    actually_allow_recreate = allow_recreate and SETTINGS.RECREATE_DATABASE

    engine_path = Path(SETTINGS.DATABASE_PATH)
    print("Database path:", engine_path)
    database_already_existed = engine_path.exists()
    fresh = not database_already_existed or actually_allow_recreate

    if actually_allow_recreate and database_already_existed:
        engine_path.unlink()

    engine = create_engine(f"sqlite:///{str(engine_path)}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    if fresh:
        imported_dbos = GoogleSheetsImporter.from_urls().import_all()
        imported_d20_dbos = GoogleSheetsImporter.from_urls().import_d20()
        with Session(engine) as session:
            session.add_all(ALL_BASE_DATA)
            session.add_all(imported_dbos)
            session.commit()

            for person in imported_d20_dbos:
                existing_person = session.exec(select(Person).where(Person.email == person.email)).first()
                if existing_person:
                    existing_person.golden_d20s = person.golden_d20s
                    session.add(existing_person)
                else:
                    session.add(person)
            session.commit()

    return fresh


@dataclass
class Option:
    name: str
    value: int | str
    checked: bool = False


T: TypeVar = TypeVar("T")


def group_by_value[T](data: list[T], key: str, sort_key: Callable[[T], Any] | None = None) -> dict[Any, list[T]]:
    grouped: dict[Any, list[T]] = {}
    for item in data:
        key_value = getattr(item, key)
        if key_value not in grouped:
            grouped[key_value] = []
        grouped[key_value].append(item)
    if sort_key:
        for key_value in grouped:
            grouped[key_value].sort(key=sort_key)
    return grouped


class StartupDBInfo:
    def __init__(self) -> None:
        with Session(engine) as session:
            self.all_games = self._get_all_games(session)
            self.game_map = self._get_game_map()

            self.table_allocations = self._get_all_table_allocations(session)

            self.table_allocations_by_timeslot: dict[int, list[TableAllocationWithExtra]] = group_by_value(
                self.table_allocations,
                "time_slot_id",
                sort_key=lambda table_allocation: table_allocation.game.title.lower(),
            )
            self.table_allocation_ids_by_timeslot: dict[int, list[int]] = {
                time_slot_id: [table_allocation.id for table_allocation in table_allocations]
                for time_slot_id, table_allocations in self.table_allocations_by_timeslot.items()
            }
            self.games_by_timeslot: dict[int, list[GameWithExtra]] = {
                time_slot_id: sorted(
                    [self.game_map[table_allocation.game_id] for table_allocation in table_allocations],
                    key=lambda game: game.title.lower(),
                )
                for time_slot_id, table_allocations in self.table_allocations_by_timeslot.items()
            }
            self.games_by_gm: dict[int, list[GameWithExtra]] = group_by_value(
                self.all_games, "gamemaster_id", sort_key=lambda game: game.title.lower()
            )
            self.games_by_gm_and_timeslot: dict[int, dict[int, list[GameWithExtra]]] = {
                gm_id: {
                    time_slot_id: [
                        game
                        for game in self.games_by_gm[gm_id]
                        if game.id
                        in [
                            table_allocation.game_id
                            for table_allocation in self.table_allocations_by_timeslot[time_slot_id]
                        ]
                    ]
                    for time_slot_id in self.table_allocations_by_timeslot
                }
                for gm_id in self.games_by_gm
            }
            self.games_by_table_allocation_id: dict[int, GameWithExtra] = {
                table_allocation.id: self.game_map[table_allocation.game_id]
                for table_allocation in self.table_allocations
            }

            self.all_genres = self._get_all_genres(session)
            self.genre_options = self._get_genre_options()
            self.all_systems = self._get_all_systems(session)
            self.system_options = self._get_system_options()
            self.all_time_slots = self._get_all_time_slots(session)
            self.time_slot_options = self._get_time_slot_options()

            self.time_slots_by_id: dict[int, TimeSlot] = {time_slot.id: time_slot for time_slot in self.all_time_slots}

    def _get_all_table_allocations(self, session: Session) -> list[TableAllocationWithExtra]:
        statement = select(TableAllocation)
        table_allocations = session.exec(statement).all()
        return [TableAllocationWithExtra.model_validate(table_allocation) for table_allocation in table_allocations]

    def _get_all_games(self, session: Session) -> list[GameWithExtra]:
        statement = select(Game).order_by(Game.title)
        games = session.exec(statement).all()
        return [GameWithExtra.model_validate(game) for game in games]

    def _get_game_map(self) -> dict[int, GameWithExtra]:
        games = self.all_games
        return {game.id: game for game in games}

    def _get_all_genres(self, session: Session) -> list[Genre]:
        statement = select(Genre).order_by(Genre.name)
        genres = session.exec(statement).all()
        return genres

    def _get_genre_options(self) -> list[Option]:
        genres = self.all_genres
        return [Option(name=genre.name, value=genre.id) for genre in genres]

    def _get_all_systems(self, session: Session) -> list[System]:
        statement = select(System).order_by(System.name)
        systems = session.exec(statement).all()
        return systems

    def _get_system_options(self) -> list[Option]:
        systems = self.all_systems
        return [Option(name=system.name, value=system.id) for system in systems]

    def _get_all_time_slots(self, session: Session) -> list[TimeSlot]:
        statement = select(TimeSlot)
        time_slots = session.exec(statement).all()
        return time_slots

    def _get_time_slot_options(self) -> list[Option]:
        time_slots = self.all_time_slots
        return [Option(name=time_slot.name, value=time_slot.id) for time_slot in time_slots]


def get_startup_db_info() -> StartupDBInfo:
    return StartupDBInfo()


if __name__ == "__main__":
    create_db_and_tables()
    print("Database created and populated.")
