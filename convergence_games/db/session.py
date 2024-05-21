import datetime as dt
from pathlib import Path
from typing import Any, Generator

from sqlmodel import Session, SQLModel, create_engine, select

from convergence_games.db.extra_types import GameCrunch
from convergence_games.db.models import Game, Genre, Person, System, TableAllocation, TimeSlot

engine = None


def get_session() -> Generator[Session, Any, None]:
    with Session(engine) as session:
        yield session


def create_db_and_tables() -> None:
    global engine
    engine_path = Path("database.db")
    if engine_path.exists():
        engine_path.unlink()
    engine = create_engine(f"sqlite:///{str(engine_path)}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)


def create_mock_db() -> None:
    if engine is None:
        create_db_and_tables()
    genre_names = ["Sci-fi", "Fantasy", "Horror", "Historical", "Modern"]
    system_names = ["D&D 5e", "Warhammer Fantasy RPG", "Board Game"]
    with Session(engine) as session:
        genre_map: dict[str, Genre] = {}
        for genre_name in genre_names:
            genre = Genre(name=genre_name)
            session.add(genre)
            genre_map[genre_name] = genre

        system_map: dict[str, System] = {}
        for system_name in system_names:
            system = System(name=system_name)
            session.add(system)
            system_map[system_name] = system

        time_slots = [
            TimeSlot(start_time=dt.datetime(2024, 1, 1, 12), end_time=dt.datetime(2024, 1, 1, 14)),
            TimeSlot(start_time=dt.datetime(2024, 1, 1, 14), end_time=dt.datetime(2024, 1, 1, 16)),
            TimeSlot(start_time=dt.datetime(2024, 1, 1, 16), end_time=dt.datetime(2024, 1, 1, 18)),
            TimeSlot(start_time=dt.datetime(2024, 1, 1, 18), end_time=dt.datetime(2024, 1, 1, 20)),
            TimeSlot(start_time=dt.datetime(2024, 1, 1, 20), end_time=dt.datetime(2024, 1, 1, 22)),
        ]
        session.add_all(time_slots)

        alice = Person(name="Alice", email="alice@email.com")
        session.add(alice)

        bob = Person(name="Bob", email="bob@email.com")
        session.add(bob)

        terraforming_mars = Game(
            title="Terraforming Mars",
            description="A game about terraforming Mars.\nIt's really good",
            crunch=GameCrunch.HEAVY,
            gamemaster=alice,
            genres=[genre_map["Sci-fi"], genre_map["Modern"]],
            system=system_map["Board Game"],
        )
        catan = Game(
            title="Catan",
            description="A game about trading",
            gamemaster=alice,
            genres=[genre_map["Modern"]],
            system=system_map["Board Game"],
        )
        dnd_5e = Game(
            title="D&D 5e",
            description="A game about adventuring",
            crunch=GameCrunch.MEDIUM,
            gamemaster=bob,
            genres=[genre_map["Fantasy"]],
            system=system_map["D&D 5e"],
        )
        session.add_all([terraforming_mars, catan, dnd_5e])

        table_allocations = [
            TableAllocation(table_number=1, slot=time_slots[0], game=terraforming_mars),
            # TableAllocation(table_number=1, slot=time_slots[0], game=catan),
            TableAllocation(table_number=2, slot=time_slots[0], game=catan),
            TableAllocation(table_number=3, slot=time_slots[1], game=dnd_5e),
        ]
        session.add_all(table_allocations)

        session.commit()


if __name__ == "__main__":
    create_mock_db()

    engine_path = Path("database.db")
    engine = create_engine(f"sqlite:///{str(engine_path)}")

    with Session(engine) as session:
        statement = select(Game)
        games = session.exec(statement).all()
        for game in games:
            print(game)
            print()
