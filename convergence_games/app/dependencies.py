from typing import Annotated

from fastapi import Depends
from sqlmodel import Session

from convergence_games.db.session import get_session

SessionDependency = Annotated[Session, Depends(get_session)]
