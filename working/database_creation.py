import asyncio

from sqlmodel import SQLModel

from convergence_games.db.session import async_session, create_db_and_tables


async def main():
    await create_db_and_tables()


if __name__ == "__main__":
    asyncio.run(main())
