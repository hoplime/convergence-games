from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DEBUG: bool = False
    DATABASE_PATH: str = "database.db"
    RECREATE_DATABASE: bool = True
    USE_HTTPS: bool = False
    INITIALISE_DATA: bool = True
    INITIAL_DATA_MODE: Literal["import", "mock"] = "import"


SETTINGS = Settings()
