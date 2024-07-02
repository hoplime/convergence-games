from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False
    DATABASE_PATH: str = "database.db"
    RECREATE_DATABASE: bool = False
    USE_HTTPS: bool = False


SETTINGS = Settings()
