from litestar import Controller, get

from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class SettingsController(Controller):
    @get(path="/settings", guards=[user_guard])
    async def get_settings(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/settings.html.jinja", block_name=request.htmx.target)
