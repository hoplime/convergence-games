from litestar import Controller, get

from convergence_games.app.response_type import HTMXBlockTemplate


class DebugController(Controller):
    path = "/debug"

    @get(path="/email-template")
    async def index(self) -> HTMXBlockTemplate:
        return HTMXBlockTemplate(
            template_name="emails/sign_in_code.html.jinja",
            context={
                "code": "123456",
                "magic_link": "https://example.com/magic_link?code=123456",
                "expires_at": "2023-10-01T00:00:00Z",
            },
        )
