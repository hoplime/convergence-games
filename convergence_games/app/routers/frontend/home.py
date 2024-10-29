from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class HomeController(Controller):
    response_headers = {"Vary": "hx-target"}

    @get(path=["/"])
    async def get_home(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/home.html.jinja", block_name=request.htmx.target)
