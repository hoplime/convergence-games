from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastui import prebuilt_html
from fastui.auth import fastapi_auth_exception_handling
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from starlette import status

from convergence_games.app.routers.games import router as games_router
from convergence_games.app.routers.main import router as main_router
from convergence_games.app.routers.my_sessions import router as sessions_router
from convergence_games.app.routers.people import router as people_router
from convergence_games.db.session import create_mock_db


@asynccontextmanager
async def lifespan(app_: FastAPI):
    create_mock_db()
    print("Mock DB created")

    async with AsyncClient() as client:
        app_.state.httpx_client = client
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


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(IntegrityError, integrity_error_handler)

fastapi_auth_exception_handling(app)
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
app.include_router(games_router)
app.include_router(people_router)
app.include_router(sessions_router)
app.include_router(main_router)


@app.get("/{path:path}")
async def html_landing() -> HTMLResponse:
    return HTMLResponse(prebuilt_html(title="Convergence Games Default Title", api_root_url="/frontend"))
