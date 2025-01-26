from litestar.router import Router

from .debug import DebugController

router = Router(
    path="/api",
    tags=["api"],
    route_handlers=[
        DebugController,
    ],
)
