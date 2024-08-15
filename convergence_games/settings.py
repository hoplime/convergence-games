from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False
    DATABASE_PATH: str = "database.db"
    RECREATE_DATABASE: bool = True
    USE_HTTPS: bool = False
    INITIALISE_DATA: bool = True
    FLAG_SCHEDULE: bool = False
    FLAG_USERS: bool = False


SETTINGS = Settings()
