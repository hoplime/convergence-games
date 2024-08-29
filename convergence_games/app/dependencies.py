from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, Security, status
from fastapi.security import APIKeyHeader
from sqlalchemy import Engine
from sqlmodel import Session as SqlModelSession
from sqlmodel import select

from convergence_games.db.models import Person
from convergence_games.db.session import get_engine, get_session
from convergence_games.settings import SETTINGS

X_API_KEY = APIKeyHeader(name="X-API-Key", auto_error=True)
X_API_KEY_ALLOW_MISSING = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_hx_target(request: Request) -> str | None:
    print("HX-Target:", request.headers.get("hx-target"))
    return request.headers.get("hx-target")


Session = Annotated[SqlModelSession, Depends(get_session)]
HxTarget = Annotated[str | None, Depends(get_hx_target)]
EngineDependency = Annotated[Engine, Depends(get_engine)]


def get_user(session: Session, email: Annotated[str | None, Cookie()] = None) -> Person | None:
    print("User with email from cookie:", email)
    if email is None:
        return None

    with session:
        statement = select(Person).where(Person.email == email)
        return session.exec(statement).first()


User = Annotated[Person | None, Depends(get_user)]


def test_api_key(x_api_key: str | None = Security(X_API_KEY)) -> bool:
    if x_api_key == SETTINGS.API_KEY:
        return True
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing or invalid API key.")


def test_api_key_with_alerts(x_api_key: str | None = Security(X_API_KEY_ALLOW_MISSING)) -> tuple[bool, list[Exception]]:
    print("Testing API key:", x_api_key)
    exceptions = []
    try:
        result = test_api_key(x_api_key)
    except Exception as e:
        exceptions.append(e)
        result = False
    return result, exceptions


Auth = Depends(test_api_key)

AuthWithHandler = Annotated[tuple[bool, list[Exception]], Depends(test_api_key_with_alerts)]
