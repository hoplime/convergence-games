from contextlib import asynccontextmanager
from pathlib import Path

import arel
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError
from starlette import status

from convergence_games.app.routes.api import router as api_router
from convergence_games.app.routes.frontend import router as frontend_router
from convergence_games.app.templates import templates
from convergence_games.db.session import create_db_and_tables, create_imported_db, get_startup_db_info
from convergence_games.settings import SETTINGS

STATIC_PATH = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app_: FastAPI):
    fresh = create_db_and_tables()

    if fresh and SETTINGS.INITIALISE_DATA:
        create_imported_db()
        print("Imported DB created")

    db = get_startup_db_info()

    yield {"db": db}
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
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=detail,
    )


app = FastAPI(lifespan=lifespan)
# app.add_middleware(HTTPSRedirectMiddleware)
app.add_exception_handler(IntegrityError, integrity_error_handler)
app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")

# Hot Reloading
if SETTINGS.DEBUG:
    hot_reload = arel.HotReload(paths=[arel.Path(".")])
    app.add_websocket_route("/hot-reload", hot_reload, name="hot-reload")
    app.add_event_handler("startup", hot_reload.startup)
    app.add_event_handler("shutdown", hot_reload.shutdown)
    templates.env.globals["DEBUG"] = SETTINGS.DEBUG
    templates.env.globals["hot_reload"] = hot_reload

# Favicons
for favicon_file in (STATIC_PATH / "favicon").iterdir():
    # We've got to bind favicon_file to the closure to avoid a late binding issue.
    def create_favicon_route(favicon_file=favicon_file):
        async def read_favicon() -> FileResponse:
            return FileResponse(favicon_file)

        return read_favicon

    app.get(f"/{favicon_file.name}", include_in_schema=False)(create_favicon_route())

app.include_router(frontend_router)
app.include_router(api_router)
