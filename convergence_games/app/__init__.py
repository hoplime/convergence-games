import os
from contextlib import asynccontextmanager
from pathlib import Path

import arel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from httpx import AsyncClient
from sqlalchemy.exc import IntegrityError
from starlette import status

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
STATIC_PATH = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

if _debug := os.environ.get("DEBUG"):
    hot_reload = arel.HotReload(paths=[arel.Path(".")])
    app.add_websocket_route("/hot-reload", hot_reload, name="hot-reload")
    app.add_event_handler("startup", hot_reload.startup)
    app.add_event_handler("shutdown", hot_reload.shutdown)
    templates.env.globals["DEBUG"] = _debug
    templates.env.globals["hot_reload"] = hot_reload

for favicon_file in (STATIC_PATH / "favicon").iterdir():
    # We've got to bind favicon_file to the closure to avoid a late binding issue.
    def create_favicon_route(favicon_file=favicon_file):
        async def read_favicon() -> FileResponse:
            return FileResponse(favicon_file)

        return read_favicon

    app.get(f"/{favicon_file.name}", include_in_schema=False)(create_favicon_route())


@app.get("/")
async def read_index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html.jinja")


@app.get("/games")
async def read_games(request: Request) -> HTMLResponse:
    return HTMLResponse("<p>WOW LOOK AT ALL THESE GAMES</p>")
