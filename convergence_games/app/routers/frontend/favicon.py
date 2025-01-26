from pathlib import Path

from litestar import Router, get
from litestar.config.response_cache import CACHE_FOREVER
from litestar.handlers import HTTPRouteHandler
from litestar.response.file import File

from convergence_games.app.paths import STATIC_DIR_PATH

route_handlers: list[HTTPRouteHandler] = []

for favicon_path in (STATIC_DIR_PATH / "favicon").iterdir():
    # We've got to bind favicon_file to the closure to avoid a late binding issue.
    def create_favicon_route(favicon_path: Path = favicon_path) -> HTTPRouteHandler:
        @get(path=f"/{favicon_path.name}", cache=CACHE_FOREVER, opt={"no_compression": True}, include_in_schema=False)
        async def favicon_route() -> File:
            return File(favicon_path)

        return favicon_route

    route_handlers.append(create_favicon_route())

favicon_router = Router(path="/", route_handlers=route_handlers)
