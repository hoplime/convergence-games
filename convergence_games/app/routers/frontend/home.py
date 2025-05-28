from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class HomeController(Controller):
    @get(path="/")
    async def get_home(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/home.html.jinja", block_name=request.htmx.target)

    @get(path="/faq")
    async def get_faq(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/faq.html.jinja", block_name=request.htmx.target)
