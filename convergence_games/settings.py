from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # General
    DEBUG: bool = False

    # Database
    DATABASE_DRIVER: str = "postgresql+asyncpg"
    DATABASE_USERNAME: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_HOST: str = ""
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = ""
    DATABASE_ECHO: bool = True

    @property
    def DATABASE_URL(self) -> URL:  # noqa: N802
        return URL.create(
            drivername=self.DATABASE_DRIVER,
            username=self.DATABASE_USERNAME,
            password=self.DATABASE_PASSWORD,
            host=self.DATABASE_HOST,
            port=self.DATABASE_PORT,
            database=self.DATABASE_NAME,
        )

    # Sqids
    SQIDS_ALPHABET: str | None = None
    SQIDS_MIN_LENGTH: int = 5

    # OAuth
    TOKEN_SECRET: str = ""
    BASE_REDIRECT_URI: str | None = "https://tolocalhost.com"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    FACEBOOK_CLIENT_ID: str = ""
    FACEBOOK_CLIENT_SECRET: str = ""
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""


SETTINGS = Settings()
