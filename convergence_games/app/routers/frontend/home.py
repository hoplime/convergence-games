from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class HomeController(Controller):
    @get(path=["/", "/test_page_1"])
    async def home(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/test_page_1.html.jinja", block_name=request.htmx.target)

    @get(path="/test_page_2")
    async def test_page_2(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/test_page_2.html.jinja", block_name=request.htmx.target)
