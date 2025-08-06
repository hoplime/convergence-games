if __name__ == "__main__":
    import asyncio

    from convergence_games.app.app import app
    from convergence_games.app.app_config.sqlalchemy_plugin import config

    asyncio.run(config.create_all_metadata(app))
