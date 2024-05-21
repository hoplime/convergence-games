from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, select
from starlette import status

from convergence_games.db.models import Game, Genre, GenreCreate, GenreRead
from convergence_games.db.session import create_mock_db, get_session


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_mock_db()
    print("Mock DB created")
    yield
    print("Shutdown")


def integrity_error_handler(request: Request, exc: IntegrityError):
    detail = {
        "code": exc.code,
        "statement": exc.statement,
        "params": exc.params,
        "orig": exc.orig.args,
        "ismulti": exc.ismulti,
        "connection_invalidated": exc.connection_invalidated,
        "message": "Integrity error occurred.",
    }
    print(detail)
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


def create_app():
    app = FastAPI(lifespan=lifespan)
    app.add_exception_handler(IntegrityError, integrity_error_handler)

    @app.get("/")
    async def read_root():
        return {"Hello": "World"}

    @app.get("/games")
    async def read_games(*, session: Session = Depends(get_session)) -> list[Game]:
        statement = select(Game)
        games = session.exec(statement).all()
        return games

    @app.post("/genres")
    async def create_genre(*, session: Session = Depends(get_session), genre: GenreCreate) -> GenreRead:
        db_genre = Genre.model_validate(genre)
        session.add(db_genre)
        session.commit()
        session.refresh(db_genre)
        return db_genre

    return app
