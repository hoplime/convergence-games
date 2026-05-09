if __name__ == "__main__":
    import asyncio

    from convergence_games.server.app import app
    from convergence_games.server.plugins import sqlalchemy_config as config

    asyncio.run(config.create_all_metadata(app))
