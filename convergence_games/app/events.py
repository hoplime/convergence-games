import random

from litestar.events import listener
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import UserEmailVerificationCode

EVENT_EMAIL_SIGN_IN = "event_email_sign_in"


@listener(EVENT_EMAIL_SIGN_IN)
async def event_email_sign_in(email: str, transaction: AsyncSession, **kwargs) -> None:
    print("event_email_sign_in, email:", email)
    new_code = "".join([random.choice("0123456789") for _ in range(6)])

    user_email_verification_code = UserEmailVerificationCode(
        code=new_code,
        email=email,
    )
    transaction.add(user_email_verification_code)
    print(f"event_email_sign_in, new_code: {new_code}")


all_listeners = [
    event_email_sign_in,
]
