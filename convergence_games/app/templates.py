from pathlib import Path
from typing import Any

import jinja_partials
from fastapi import Request
from jinja2 import pass_context
from jinja2_fragments.fastapi import Jinja2Blocks

from convergence_games.settings import SETTINGS

templates = Jinja2Blocks(directory=Path(__file__).parent / "templates")
jinja_partials.register_starlette_extensions(templates)

if SETTINGS.USE_HTTPS:

    @pass_context
    def urlx_for(context: dict, name: str, **path_params: Any) -> str:
        request: Request = context["request"]
        http_url = request.url_for(name, **path_params)
        return http_url.replace(scheme="https")

    templates.env.globals["url_for"] = urlx_for

templates.env.globals["FLAG_SCHEDULE"] = SETTINGS.FLAG_SCHEDULE
templates.env.globals["FLAG_USERS"] = SETTINGS.FLAG_USERS
