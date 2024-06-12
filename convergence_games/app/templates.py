from pathlib import Path

import jinja_partials
from jinja2_fragments.fastapi import Jinja2Blocks

templates = Jinja2Blocks(directory=Path(__file__).parent / "templates")
jinja_partials.register_starlette_extensions(templates)
