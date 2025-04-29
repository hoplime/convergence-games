from functools import cached_property
from typing import Literal, Self

from pydantic import AwareDatetime, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    # Website
    BASE_DOMAIN: str = "http://localhost:8000"

    # General
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "production"] = "development"
    LAST_UPDATED: AwareDatetime | None = None
    USE_CACHE_BUSTED_FILES: bool = False

    @cached_property
    def RELEASE(self) -> str:  # noqa: N802
        """Get the release version from the last updated date."""
        if self.LAST_UPDATED:
            return self.LAST_UPDATED.strftime("%Y.%m.%d+%H.%M.%S")
        return "unknown"

    @cached_property
    def LIB_JS(self) -> str:  # noqa: N802
        """Get the lib.js file path."""
        if self.USE_CACHE_BUSTED_FILES:
            return f"/static/js/lib.{self.RELEASE}.js"
        return "/static/js/lib.js"

    @cached_property
    def STYLE_CSS(self) -> str:  # noqa: N802
        """Get the style.css file path."""
        if self.USE_CACHE_BUSTED_FILES:
            return f"/static/css/style.{self.RELEASE}.css"
        return "/static/css/style.css"

    # Database
    DATABASE_DRIVER: str = "postgresql+asyncpg"
    DATABASE_USERNAME: str = ""
    DATABASE_PASSWORD: str = ""
    DATABASE_HOST: str = ""
    DATABASE_PORT: int = 5432
    DATABASE_NAME: str = ""
    DATABASE_ECHO: bool = False

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
    SIGNING_KEY: str = ""
    TOKEN_SECRET: str = ""
    BASE_REDIRECT_URI: str | None = "https://tolocalhost.com"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    FACEBOOK_CLIENT_ID: str = ""
    FACEBOOK_CLIENT_SECRET: str = ""
    DISCORD_CLIENT_ID: str = ""
    DISCORD_CLIENT_SECRET: str = ""

    # Email
    BREVO_API_KEY: str = ""
    BREVO_SENDER_NAME: str = "Waikato Role-Playing Guild"
    BREVO_SENDER_EMAIL: str = "noreply@waikatorpg.co.nz"

    # Sentry
    SENTRY_ENABLE: bool = True
    SENTRY_ENVIRONMENT: str = ""
    # Backend settings
    SENTRY_DSN: str = ""
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0
    SENTRY_PROFILES_SAMPLE_RATE: float = 1.0
    SENTRY_SEND_DEFAULT_PII: bool = True
    # Frontend settings
    SENTRY_LOADER_SRC: str = ""
    SENTRY_REPLAYS_SESSION_SAMPLE_RATE: float = 1.0
    SENTRY_REPLAYS_ON_ERROR_SAMPLE_RATE: float = 1.0

    @model_validator(mode="after")
    def set_default_sentry_environment(self) -> Self:
        """Set the default Sentry environment to the current environment."""
        if not self.SENTRY_ENVIRONMENT:
            self.SENTRY_ENVIRONMENT = self.ENVIRONMENT
        return self


SETTINGS = Settings()
