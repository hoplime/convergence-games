import datetime as dt
import random
import zoneinfo

import httpx
from litestar.events import listener
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.app_config.template_config import jinja_env
from convergence_games.db.models import UserEmailVerificationCode
from convergence_games.settings import SETTINGS

EVENT_EMAIL_SIGN_IN = "event_email_sign_in"


@listener(EVENT_EMAIL_SIGN_IN)
async def event_email_sign_in(email: str, transaction: AsyncSession, tz: dt.tzinfo | None = None, **kwargs) -> None:
    code = "".join([random.choice("0123456789") for _ in range(6)])

    user_email_verification_code = UserEmailVerificationCode(
        code=code,
        email=email,
    )
    transaction.add(user_email_verification_code)
    await transaction.commit()
    await transaction.refresh(user_email_verification_code)

    print(f"event_email_sign_in, email: {email}, new_code: {code}")
    magic_link_code = UserEmailVerificationCode.generate_magic_link_code(code, email)
    magic_link_url = f"{SETTINGS.BASE_DOMAIN}/email_auth/magic_link?code={magic_link_code}"

    if tz is None:
        tz = zoneinfo.ZoneInfo("Pacific/Auckland")
    formatted_expires_at = user_email_verification_code.expires_at.astimezone(tz).strftime("%a %B %d %I:%M%p %Z")
    html_content = jinja_env.get_template("emails/sign_in_code.html.jinja").render(
        magic_link_url=magic_link_url,
        code=code,
        expires_at=formatted_expires_at,
    )

    async with httpx.AsyncClient() as client:
        await client.post(
            url="https://api.brevo.com/v3/smtp/email",
            headers={
                "accept": "application/json",
                "api-key": SETTINGS.BREVO_API_KEY,
                "content-type": "application/json",
            },
            json={
                "sender": {"name": SETTINGS.BREVO_SENDER_NAME, "email": SETTINGS.BREVO_SENDER_EMAIL},
                "to": [{"email": email}],
                "subject": "Your sign-in code for Convergence",
                "htmlContent": html_content,
            },
        )


all_listeners = [
    event_email_sign_in,
]
