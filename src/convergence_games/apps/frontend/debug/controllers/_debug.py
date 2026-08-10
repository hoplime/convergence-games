from litestar import Controller, get

from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template


class DebugController(Controller):
    path = "/debug"

    @get(path="/email-template")
    async def get_email_template(self) -> HTMXBlockTemplate:
        return HTMXBlockTemplate(
            template_name="emails/sign_in_code.html.jinja",
            context={
                "code": "123456",
                "magic_link": "https://example.com/magic_link?code=123456",
                "expires_at": "2023-10-01T00:00:00Z",
            },
        )

    @get(path="/editor-test")
    async def get_editor_test(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/editor_test.html.jinja", block_name=request.htmx.target)
