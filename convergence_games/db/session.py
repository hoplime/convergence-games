from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from convergence_games.settings import SETTINGS

engine = create_async_engine(SETTINGS.DATABASE_URL)
session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
