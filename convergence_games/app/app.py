from __future__ import annotations

import random
from collections.abc import AsyncGenerator

from litestar import Litestar, get
from litestar.contrib.htmx.request import HTMXRequest
from litestar.response import Template
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.htmx_block_template import HTMXBlockTemplate
from convergence_games.db.models import Genre

from .app_config.openapi_config import openapi_config
from .app_config.sqlalchemy_plugin import sqlalchemy_plugin
from .app_config.static_files_router import static_files_router
from .app_config.template_config import template_config
from .context import user_id_ctx


@get("/test_page_1")
async def test_page_1(request: HTMXRequest) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_1.html.jinja", block_name=request.htmx.target)


@get("/test_page_2")
async def test_page_2(request: HTMXRequest) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_2.html.jinja", block_name=request.htmx.target)


@get("/db_test")
async def db_test(db_session_with_user: AsyncSession) -> str:
    async with db_session_with_user.begin():
        random_genre = Genre(
            name=random.choice(["Action", "Adventure", "Horror", "Mystery", "Romance", "Sci-Fi", "Thriller"])
            + " "
            + str(random.randint(1, 1000)),
            description="A genre of fiction whose content is the interest of the audience or business.",
        )
        db_session_with_user.add(random_genre)
        await db_session_with_user.flush()
        genre_id = random_genre.id
    return f"DB Test Page for user {user_id_ctx.get()} - Added Genre ID: {genre_id}"


# TODO - This is a temporary solution to inject the user_id into the session
async def db_session_with_user(db_session: AsyncSession) -> AsyncGenerator[AsyncSession]:
    print(f"B {user_id_ctx.get()=}")
    t = user_id_ctx.set(1)
    print(f"C {user_id_ctx.get()=}")
    yield db_session
    user_id_ctx.reset(t)
    print(f"D {user_id_ctx.get()=}")


print(f"A {user_id_ctx.get()=}")

app = Litestar(
    route_handlers=[static_files_router, test_page_1, test_page_2, db_test],
    dependencies={
        "db_session_with_user": db_session_with_user,
    },
    request_class=HTMXRequest,
    plugins=[sqlalchemy_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    debug=True,
)
