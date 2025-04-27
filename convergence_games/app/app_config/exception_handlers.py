from litestar import Response
from litestar.datastructures import Cookie
from litestar.response import Redirect

from convergence_games.app.exceptions import UserNotLoggedInError
from convergence_games.app.request_type import Request


def user_not_logged_in_handler(request: Request, exc: UserNotLoggedInError) -> Response:
    """Handle UserNotLoggedInError by redirecting to the login page."""
    request_url_path = request.scope["path"]
    return Redirect(path="/profile", cookies=[Cookie(key="invalid-action-path", value=request_url_path, max_age=30)])


exception_handlers = {
    UserNotLoggedInError: user_not_logged_in_handler,
}
