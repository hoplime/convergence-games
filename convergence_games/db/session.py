import datetime as dt
import random
from csv import DictReader
from pathlib import Path
from typing import Any, Generator

from sqlmodel import Session, SQLModel, create_engine, select

from convergence_games.db.extra_types import GameCrunch, GameNarrativism, GameTone
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


def create_mock_time_slots(session: Session) -> list[TimeSlot]:
    time_slots = [
        TimeSlot(
            name="Saturday Morning",
            start_time=dt.datetime(2024, 9, 7, 9),
            end_time=dt.datetime(2024, 9, 7, 12),
        ),
        TimeSlot(
            name="Saturday Afternoon",
            start_time=dt.datetime(2024, 9, 7, 13),
            end_time=dt.datetime(2024, 9, 7, 16),
        ),
        TimeSlot(
            name="Saturday Evening",
            start_time=dt.datetime(2024, 9, 7, 17),
            end_time=dt.datetime(2024, 9, 7, 21),
        ),
        TimeSlot(
            name="Sunday Morning",
            start_time=dt.datetime(2024, 9, 8, 9),
            end_time=dt.datetime(2024, 9, 8, 12),
        ),
        TimeSlot(
            name="Sunday Afternoon",
            start_time=dt.datetime(2024, 9, 8, 13),
            end_time=dt.datetime(2024, 9, 8, 16),
        ),
    ]
    session.add_all(time_slots)
    return time_slots


def create_mock_db() -> None:
    if engine is None:
        create_db_and_tables()

    with Session(engine) as session:
        gm_map: dict[str, Person] = {}
        genre_map: dict[str, Genre] = {}
        system_map: dict[str, System] = {}
        game_map: dict[str, Game] = {}

        with open("mock_data/Mock Convergence Data - GMs.csv") as f:
            for row in DictReader(f):
                person = Person(name=row["name"], email=row["email"])
                gm_map[row["name"]] = person

        session.add_all(gm_map.values())

        with open("mock_data/Mock Convergence Data - Games.csv") as f:
            for row in DictReader(f):
                genre_names = [name.strip() for name in row["genres"].split(",")]
                system_name = row["system"]
                crunch = random.choice(list(GameCrunch))
                narrativism = random.choice(list(GameNarrativism))
                tone = random.choice(list(GameTone))
                gamemaster_name = row["gamemaster"]
                title = row["title"]
                description = row["description"]
                age_suitability = row["age_suitability"]

                if system_name not in system_map:
                    system = System(name=system_name)
                    system_map[system_name] = system

                for genre_name in genre_names:
                    if genre_name not in genre_map:
                        genre = Genre(name=genre_name)
                        genre_map[genre_name] = genre

                gamemaster = gm_map[gamemaster_name]

                game = Game(
                    title=title,
                    description=description,
                    crunch=crunch,
                    narrativism=narrativism,
                    tone=tone,
                    age_suitability=age_suitability,
                    gamemaster=gamemaster,
                    genres=[genre_map[genre_name] for genre_name in genre_names],
                    system=system_map[system_name],
                )
                game_map[title] = game

        session.add_all(system_map.values())
        session.add_all(genre_map.values())
        session.add_all(game_map.values())

        time_slots = create_mock_time_slots(session)
        with open("mock_data/Mock Convergence Data - Tables.csv") as f:
            for row in DictReader(f):
                table_number = row["table_number"]
                for i, time_slot in enumerate(time_slots):
                    game = game_map[row[f"time_slot_{i}"]]
                    table_allocation = TableAllocation(
                        table_number=table_number,
                        game=game,
                        time_slot=time_slot,
                    )
                    session.add(table_allocation)

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
