from litestar.datastructures import CacheControlHeader
from litestar.static_files import create_static_files_router

from convergence_games.app.paths import STATIC_DIR_PATH

static_files_router = create_static_files_router(
    path="/static",
    directories=[STATIC_DIR_PATH],
    cache_control=CacheControlHeader(max_age=120),
)
