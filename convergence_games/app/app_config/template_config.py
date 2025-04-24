import uuid
from typing import Any

import jinjax
from humanize import naturaldelta
from jinja2 import Environment, FileSystemLoader
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.template.config import TemplateConfig

from convergence_games.app.paths import COMPONENTS_DIR_PATH, TEMPLATES_DIR_PATH
from convergence_games.db.ocean import swim
from convergence_games.settings import SETTINGS
from convergence_games.utils.time_utils import nice_time_format, time_range_format


def extract_title(text: jinjax.catalog.CallerWrapper) -> str:
    title_start = text.find("<title>")
    if not title_start:
        return ""
    title_end = text.find("</title>", title_start)
    return text._content[title_start + 7 : title_end]


def debug(text: Any) -> Any:
    print(text)
    return text


original_init = jinjax.Component.__init__


class ComponentWithRequestPassthrough(jinjax.Component):
    def __init__(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.optional["request"] = None


jinjax.Component.__init__ = ComponentWithRequestPassthrough.__init__  # type: ignore


class JinjaXWithRequestPassthrough(jinjax.JinjaX):
    def _build_call(self, tag, attrs_list, content=""):
        attrs_list.append(("request", "{{ request }}"))
        return super()._build_call(tag, attrs_list, content)


jinja_env = Environment(
    loader=FileSystemLoader(searchpath=TEMPLATES_DIR_PATH),
    extensions=[
        JinjaXWithRequestPassthrough,
    ],
    trim_blocks=True,
    lstrip_blocks=True,
)

jinja_env.filters["debug"] = debug
jinja_env.filters["extract_title"] = extract_title
jinja_env.filters["nice_time_format"] = nice_time_format
jinja_env.filters["time_range_format"] = time_range_format
jinja_env.filters["humanize"] = naturaldelta

jinja_env.globals["swim"] = swim
jinja_env.globals["random_id"] = lambda: str(uuid.uuid4())
jinja_env.globals["SETTINGS"] = SETTINGS

catalog = jinjax.Catalog(jinja_env=jinja_env)
catalog.add_folder(COMPONENTS_DIR_PATH)

template_engine = JinjaTemplateEngine.from_environment(jinja_env)

template_config = TemplateConfig(engine=template_engine)
