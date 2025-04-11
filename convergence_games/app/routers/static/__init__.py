from litestar.router import Router

from .favicon import favicon_router
from .static import static_files_router

router = Router(
    path="/",
    response_headers={"Vary": "hx-target"},
    include_in_schema=False,
    tags=["static"],
    route_handlers=[
        favicon_router,
        static_files_router,
    ],
)
