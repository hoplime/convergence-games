from pathlib import Path
from typing import Any

import jinja2
import jinjax
from fastapi import Request
from jinja2_fragments.fastapi import Jinja2Blocks

from convergence_games.settings import SETTINGS

templates = Jinja2Blocks(directory=Path(__file__).parent / "templates")

templates.env.add_extension(jinjax.JinjaX)

if SETTINGS.USE_HTTPS:

    @jinja2.pass_context
    def url_for_https(context: dict, name: str, **path_params: Any) -> str:
        request: Request = context["request"]
        http_url = request.url_for(name, **path_params)
        return str(http_url.replace(scheme="https"))

    templates.env.globals["url_for"] = url_for_https


def debug(text: Any) -> str:
    return ""


def extract_title(text: jinjax.catalog.CallerWrapper) -> str:
    title_start = text.find("<title>")
    if not title_start:
        return ""
    title_end = text.find("</title>", title_start)
    return text._content[title_start + 7 : title_end]


templates.env.filters["debug"] = debug
templates.env.filters["extract_title"] = extract_title


catalog = jinjax.Catalog(jinja_env=templates.env)
catalog.add_folder(Path(__file__).parent / "templates/components")
