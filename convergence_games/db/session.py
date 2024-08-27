from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from convergence_games.db.base_data import ALL_BASE_DATA
from convergence_games.db.models import Game, GameWithExtra, Genre, System, TimeSlot
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
        with Session(engine) as session:
            session.add_all(ALL_BASE_DATA)
            session.add_all(imported_dbos)
            session.commit()

    return fresh


@dataclass
class Option:
    name: str
    value: int | str
    checked: bool = False


class StartupDBInfo:
    def __init__(self) -> None:
        with Session(engine) as session:
            self.all_games = self._get_all_games(session)
            self.game_map = self._get_game_map()

            self.all_genres = self._get_all_genres(session)
            self.genre_options = self._get_genre_options()
            self.all_systems = self._get_all_systems(session)
            self.system_options = self._get_system_options()
            self.all_time_slots = self._get_all_time_slots(session)
            self.time_slot_options = self._get_time_slot_options()

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
