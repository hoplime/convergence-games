from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlmodel import Session as SqlModelSession
from sqlmodel import select

from convergence_games.db.models import Person
from convergence_games.db.session import get_session

X_API_KEY = APIKeyHeader(name="X-API-Key", auto_error=True)


def get_hx_target(request: Request) -> str | None:
    print("HX-Target:", request.headers.get("hx-target"))
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


def test_api_key(x_api_key: str | None = Security(X_API_KEY)) -> bool:
    if x_api_key in ("SUPER SECRET API", "a"):
        return True
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing or invalid API key.")


Auth = Depends(test_api_key)
