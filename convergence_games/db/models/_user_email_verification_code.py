from __future__ import annotations

import datetime as dt
from base64 import urlsafe_b64decode, urlsafe_b64encode

from advanced_alchemy.types import DateTimeUTC
from sqlalchemy.orm import Mapped, mapped_column, validates

from ._base import Base


class UserEmailVerificationCode(Base):
    code: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(index=True)
    expires_at: Mapped[dt.datetime] = mapped_column(
        DateTimeUTC(timezone=True),
        default=lambda: dt.datetime.now(tz=dt.timezone.utc) + dt.timedelta(hours=4),
    )

    @validates("expires_at")
    def validate_tz_info(self, _: str, value: dt.datetime) -> dt.datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.timezone.utc)
        return value

    @staticmethod
    def generate_magic_link_code(code: str, email: str) -> str:
        # Encode the code and email in base64
        code = f"{code}:{email}"
        encoded_code = urlsafe_b64encode(code.encode()).decode()
        return encoded_code

    @staticmethod
    def decode_magic_link_code(magic_link_code: str) -> tuple[str, str]:
        # Decode the code from base64
        decoded_code = urlsafe_b64decode(magic_link_code.encode()).decode()
        code, email = decoded_code.split(":", 1)
        return code, email
