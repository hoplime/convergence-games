from dataclasses import dataclass
from typing import Annotated, Literal, Sequence

from litestar import Controller, get, post
from litestar.exceptions import HTTPException
from litestar.params import Body, RequestEncodingType
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.app.events import EVENT_EMAIL_SIGN_IN
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.models import UserLogin


class SettingsController(Controller):
    @get(path="/settings")
    async def get_settings(self, request: Request) -> Template:
        if request.user is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        return HTMXBlockTemplate(template_name="pages/settings.html.jinja", block_name=request.htmx.target)
