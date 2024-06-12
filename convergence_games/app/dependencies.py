from typing import Annotated

from fastapi import Depends, Request
from sqlmodel import Session as SqlModelSession

from convergence_games.db.session import get_session


def get_hx_target(request: Request) -> str | None:
    return request.headers.get("hx-target")


Session = Annotated[SqlModelSession, Depends(get_session)]
HxTarget = Annotated[str | None, Depends(get_hx_target)]
