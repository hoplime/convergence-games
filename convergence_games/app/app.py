from __future__ import annotations

import random

from litestar import Litestar, get
from litestar.response import Template
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.context import user_id_ctx
from convergence_games.app.htmx_block_template import HTMXBlockTemplate
from convergence_games.app.request_type import Request
from convergence_games.db.models import Genre, User

from .app_config.mock_authentication_middleware import mock_authentication_middleware
from .app_config.openapi_config import openapi_config
from .app_config.sqlalchemy_plugin import sqlalchemy_plugin
from .app_config.static_files_router import static_files_router
from .app_config.template_config import template_config

# from .app_config.user_plugin import user_plugin


@get("/test_page_1")
async def test_page_1(request: Request) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_1.html.jinja", block_name=request.htmx.target)


@get("/test_page_2")
async def test_page_2(request: Request) -> Template:
    return HTMXBlockTemplate(template_name="pages/test_page_2.html.jinja", block_name=request.htmx.target)


# @get("/db_test")
# async def db_test_no_dep(db_session: AsyncSession, user: User | None) -> str:
#     if user is None:
#         return "DB Test Page with no dependencies No User"

#     print(f"F {user.id}")
#     async with db_session.begin():
#         print(f"G {user.name}")
#         random_genre = Genre(
#             name=random.choice(["Action", "Adventure", "Horror", "Mystery", "Romance", "Sci-Fi", "Thriller"])
#             + " "
#             + str(random.randint(1, 1000)),
#             description="A genre of fiction whose content is the interest of the audience or business.",
#         )
#         db_session.add(random_genre)
#         await db_session.flush()
#         genre_id = random_genre.id
#         print(random_genre.name)
#     return f"DB Test Page with no dependencies {user.id} {genre_id}"


@get("/db_test")
async def db_test_no_dep(request: Request, db_session: AsyncSession) -> str:
    print(request.state.dict())
    print(request.user)
    print(request.auth)
    print(user_id_ctx.get())
    stmt = select(User).where(User.id == user_id_ctx.get())
    user = (await db_session.execute(stmt)).scalar_one_or_none()

    if user is None:
        return "DB Test Page with no dependencies No User"

    print(user)
    random_genre = Genre(
        name=random.choice(["Action", "Adventure", "Horror", "Mystery", "Romance", "Sci-Fi", "Thriller"])
        + " "
        + str(random.randint(1, 1000)),
        description="A genre of fiction whose content is the interest of the audience or business.",
    )
    db_session.add(random_genre)
    await db_session.flush()
    genre_id = random_genre.id
    print(random_genre.name)
    return f"DB Test Page with no dependencies {user.id} {genre_id}"


app = Litestar(
    route_handlers=[static_files_router, test_page_1, test_page_2, db_test_no_dep],
    dependencies={},
    request_class=Request,
    middleware=[mock_authentication_middleware],
    plugins=[sqlalchemy_plugin],  # , user_plugin],
    openapi_config=openapi_config,
    template_config=template_config,
    debug=True,
)
