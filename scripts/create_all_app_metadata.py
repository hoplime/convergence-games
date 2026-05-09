if __name__ == "__main__":
    import asyncio

    from convergence_games.server.app import app
    from convergence_games.server.config import sqlalchemy as config

    asyncio.run(config.create_all_metadata(app))
