from litestar.router import Router

from ._favicon import favicon_router
from ._health import health_check
from ._static import static_files_router

router = Router(
    path="/",
    include_in_schema=False,
    tags=["system"],
    route_handlers=[
        favicon_router,
        health_check,
        static_files_router,
    ],
)
