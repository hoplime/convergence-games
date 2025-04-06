from litestar import Controller, get

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template


class EditorTestController(Controller):
    @get(path="/editor_test")
    async def get_editor_test(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/editor_test.html.jinja", block_name=request.htmx.target)
