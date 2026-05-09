from litestar.datastructures import Cookie
from litestar.response import Redirect

from convergence_games.lib.alerts import AlertError
from convergence_games.lib.exceptions import UserNotLoggedInError
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate
from convergence_games.server._template import catalog

__all__ = ["exception_handlers"]


def user_not_logged_in_handler(request: Request, exc: UserNotLoggedInError) -> Redirect:
    """Handle UserNotLoggedInError by redirecting to the login page."""
    request_url_path = request.scope["path"]
    return Redirect(path="/profile", cookies=[Cookie(key="invalid-action-path", value=request_url_path, max_age=30)])


def alert_handler(request: Request, exc: AlertError) -> HTMXBlockTemplate:
    template_str = catalog.render(
        "ToastAlerts",
        alerts=exc.alerts,
        redirect_text=(exc.redirect_text or "Return Home") if not request.htmx else "",
        redirect_url=(exc.redirect_url or "/") if not request.htmx else "",
    )
    return HTMXBlockTemplate(
        template_str=template_str,
        re_target=request.query_params.get("alert-retarget", "#content"),
        re_swap="beforeend",
    )


exception_handlers = {
    UserNotLoggedInError: user_not_logged_in_handler,
    AlertError: alert_handler,
}
