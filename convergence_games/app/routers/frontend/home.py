from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class HomeController(Controller):
    @get(path=["/"])
    async def home(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/home.html.jinja", block_name=request.htmx.target)

    @get(path="/games")
    async def games(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/games.html.jinja", block_name=request.htmx.target)

    @get(path="/profile")
    async def profile(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/profile.html.jinja", block_name=request.htmx.target)
