import random

import httpx
from litestar.events import listener
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import UserEmailVerificationCode
from convergence_games.settings import SETTINGS

EVENT_EMAIL_SIGN_IN = "event_email_sign_in"


@listener(EVENT_EMAIL_SIGN_IN)
async def event_email_sign_in(email: str, transaction: AsyncSession, **kwargs) -> None:
    new_code = "".join([random.choice("0123456789") for _ in range(6)])

    user_email_verification_code = UserEmailVerificationCode(
        code=new_code,
        email=email,
    )
    transaction.add(user_email_verification_code)
    await transaction.commit()
    print(f"event_email_sign_in, email: {email}, new_code: {new_code}")
    magic_link_code = UserEmailVerificationCode.generate_magic_link_code(new_code, email)
    magic_link_url = f"{SETTINGS.BASE_DOMAIN}/email_auth/magic_link?code={magic_link_code}"

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
                "htmlContent": f"""
                    <html>
                        <head></head>
                        <body>
                            <p>Click the link below to sign in:</p>
                            <a href="{magic_link_url}">Sign in</a>
                            <p>Or copy and paste the code below:</p>
                            <p>{new_code}</p>
                        </body>
                    </html>
                """,
            },
        )


all_listeners = [
    event_email_sign_in,
]
