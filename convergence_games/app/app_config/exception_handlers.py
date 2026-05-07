from litestar.datastructures import Cookie
from litestar.response import Redirect
from litestar.status_codes import HTTP_301_MOVED_PERMANENTLY

from convergence_games.app.alerts import AlertError
from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.exceptions import SlugRedirectError, UserNotLoggedInError
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate


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


def slug_redirect_handler(request: Request, exc: SlugRedirectError) -> Redirect:
    """301-redirect from a sqid-form URL to its canonical slug-form URL."""
    return Redirect(path=exc.path, status_code=HTTP_301_MOVED_PERMANENTLY)


exception_handlers = {
    UserNotLoggedInError: user_not_logged_in_handler,
    AlertError: alert_handler,
    SlugRedirectError: slug_redirect_handler,
}
