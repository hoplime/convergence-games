import os
from contextlib import asynccontextmanager
from logging import getLogger
from pathlib import Path

import arel
import sentry_sdk
from azure.monitor.opentelemetry import configure_azure_monitor
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.trace import (
    get_tracer_provider,
)
from sqlalchemy.exc import IntegrityError
from starlette import status

from convergence_games.app.routes.api import router as api_router
from convergence_games.app.routes.frontend import router as frontend_router
from convergence_games.app.templates import templates
from convergence_games.db.session import create_db_and_tables, get_startup_db_info
from convergence_games.settings import SETTINGS

if SETTINGS.ENABLE_SENTRY:
    sentry_sdk.init(
        dsn=SETTINGS.SENTRY_DSN,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for tracing.
        traces_sample_rate=1.0,
        # Set profiles_sample_rate to 1.0 to profile 100%
        # of sampled transactions.
        # We recommend adjusting this value in production.
        profiles_sample_rate=1.0,
        environment=SETTINGS.ENVIRONMENT_NAME,
    )

STATIC_PATH = Path(__file__).parent / "static"

if os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING") and SETTINGS.ENABLE_APP_INSIGHTS:
    print("Will configure Azure Monitor")
    configure_azure_monitor()

    tracer = trace.get_tracer(__name__, tracer_provider=get_tracer_provider())
    logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(app_: FastAPI):
    create_db_and_tables()

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

if SETTINGS.ENABLE_APP_INSIGHTS:
    FastAPIInstrumentor.instrument_app(app)

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


@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
