if __name__ == "__main__":
    import asyncio

    from convergence_games.server import app
    from convergence_games.server import sqlalchemy_config as config

    asyncio.run(config.create_all_metadata(app))
