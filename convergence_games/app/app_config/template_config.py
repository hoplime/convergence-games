from pathlib import Path
from typing import Any

import jinjax
from jinja2 import Environment, FileSystemLoader
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig


def extract_title(text: jinjax.catalog.CallerWrapper) -> str:
    title_start = text.find("<title>")
    if not title_start:
        return ""
    title_end = text.find("</title>", title_start)
    return text._content[title_start + 7 : title_end]


def debug(text: Any) -> str:
    print(text)
    return ""


TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
COMPONENTS_DIR = TEMPLATES_DIR / "components"

jinja_env = Environment(
    loader=FileSystemLoader(searchpath=TEMPLATES_DIR),
    extensions=[
        jinjax.JinjaX,
    ],
)

jinja_env.filters["debug"] = debug
jinja_env.filters["extract_title"] = extract_title

catalog = jinjax.Catalog(jinja_env=jinja_env)
catalog.add_folder(COMPONENTS_DIR)

template_engine = JinjaTemplateEngine.from_environment(jinja_env)

template_config = TemplateConfig(engine=template_engine)
