from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class ProfileController(Controller):
    @get(path="/profile")
    async def get_profile(self, request: Request) -> Template:
        if request.user is None:
            return HTMXBlockTemplate(template_name="pages/register.html.jinja", block_name=request.htmx.target)
        return HTMXBlockTemplate(template_name="pages/profile.html.jinja", block_name=request.htmx.target)
