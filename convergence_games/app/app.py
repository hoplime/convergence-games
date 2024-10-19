from __future__ import annotations

from litestar import Litestar, get
from litestar.contrib.htmx.request import HTMXRequest
from litestar.response import Template

from convergence_games.app.htmx_block_template import HTMXBlockTemplate

from .app_config.openapi_config import openapi_config
from .app_config.sqlalchemy_plugin import sqlalchemy_plugin
from .app_config.static_files_router import static_files_router
from .app_config.template_config import template_config


@get("/test_page_1")
async def test_page_1(request: HTMXRequest) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_1.html.jinja", block_name=request.htmx.target)


@get("/test_page_2")
async def test_page_2(request: HTMXRequest) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_2.html.jinja", block_name=request.htmx.target)


app = Litestar(
    route_handlers=[static_files_router, test_page_1, test_page_2],
    request_class=HTMXRequest,
    plugins=[sqlalchemy_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    debug=True,
)
