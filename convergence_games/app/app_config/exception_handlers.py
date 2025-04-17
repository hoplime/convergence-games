from litestar import Response
from litestar.datastructures import Cookie
from litestar.response import Redirect

from convergence_games.app.exceptions import UserNotLoggedInError
from convergence_games.app.request_type import Request


def user_not_logged_in_handler(_: Request, exc: UserNotLoggedInError) -> Response:
    """Handle UserNotLoggedInError by redirecting to the login page."""
    return Redirect(path="/profile", cookies=[Cookie(key="did-invalid-action", value="True", max_age=30)])


exception_handlers = {
    UserNotLoggedInError: user_not_logged_in_handler,
}
