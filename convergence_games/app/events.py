from litestar.events import listener

EVENT_EMAIL_SIGN_IN = "event_email_sign_in"


@listener(EVENT_EMAIL_SIGN_IN)
async def event_email_sign_in(email: str, **kwargs) -> None:
    print("event_email_sign_in, email:", email)


all_listeners = [
    event_email_sign_in,
]
