from sqlalchemy.engine import URL
from sqlmodel import Session, SQLModel, create_engine, insert, select

from convergence_games.db.models import (
    AdventuringGroup,
    AllocationResult,
    CommittedAllocationResult,
    Compensation,
    ContentWarning,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    Genre,
    Person,
    PersonAdventuringGroupLink,
    SessionPreference,
    System,
    Table,
    TableAllocation,
    TimeSlot,
)
from convergence_games.settings import SETTINGS

connection_string = URL.create(
    drivername="postgresql+psycopg2",
    username=SETTINGS.DATABASE_USERNAME,
    password=SETTINGS.DATABASE_PASSWORD,
    host=SETTINGS.DATABASE_HOST,
    port=5432,
    database=SETTINGS.DATABASE_NAME,
)
postgres_engine = create_engine(connection_string)
SQLModel.metadata.create_all(postgres_engine)

sqlite_connection_string = f"sqlite:///{SETTINGS.DATABASE_NAME}.db"
sqlite_engine = create_engine(sqlite_connection_string)
SQLModel.metadata.create_all(sqlite_engine)

with Session(postgres_engine) as p_session, Session(sqlite_engine) as s_session:
    for table_class in [
        AdventuringGroup,
        AllocationResult,
        CommittedAllocationResult,
        Compensation,
        ContentWarning,
        Game,
        GameContentWarningLink,
        GameGenreLink,
        Genre,
        Person,
        PersonAdventuringGroupLink,
        SessionPreference,
        System,
        Table,
        TableAllocation,
        TimeSlot,
    ]:
        postgres_rows = p_session.exec(select(table_class)).all()
        statement = insert(table_class).values([row.model_dump() for row in postgres_rows])
        s_session.exec(statement)
    s_session.commit()
