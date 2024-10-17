from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel

from convergence_games.db.models import *  # noqa: F403 - We need to import something from the models to create the tables
from convergence_games.settings import SETTINGS

engine: AsyncEngine | None = None


@asynccontextmanager
async def async_session() -> AsyncGenerator[AsyncSession]:
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


async def create_db_and_tables() -> None:
    global engine

    engine = create_async_engine(
        SETTINGS.DATABASE_URL,
        echo=SETTINGS.DATABASE_ECHO,
        future=True,  # TODO: Setting?
        pool_size=20,  # TODO: Setting?
        max_overflow=20,  # TODO: Setting?
        pool_recycle=3600,  # TODO: Setting?
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
