from typing import Annotated

from fastapi import Cookie, Depends, Request
from sqlmodel import Session as SqlModelSession
from sqlmodel import select

from convergence_games.db.models import Person
from convergence_games.db.session import get_session


def get_hx_target(request: Request) -> str | None:
    return request.headers.get("hx-target")


Session = Annotated[SqlModelSession, Depends(get_session)]
HxTarget = Annotated[str | None, Depends(get_hx_target)]


def get_user(session: Session, email: Annotated[str | None, Cookie()] = None) -> Person | None:
    print("User with email from cookie:", email)
    if email is None:
        return None

    with session:
        statement = select(Person).where(Person.email == email)
        return session.exec(statement).first()


User = Annotated[Person | None, Depends(get_user)]
