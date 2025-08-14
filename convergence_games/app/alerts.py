from dataclasses import dataclass
from typing import Literal

from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate


@dataclass
class Alert:
    alert_class: Literal["alert-success", "alert-info", "alert-warning", "alert-error"]
    message: str


def alerts_response(alerts: list[Alert], request: Request | None = None) -> HTMXBlockTemplate:
    """
    Generates an HTMX response with a list of alerts.

    Args:
        alerts: A list of Alert objects to be displayed.
        request: The request object containing user information.

    Returns:
        An HTMXBlockTemplate containing the rendered alerts.
    """
    template_str = catalog.render("ToastAlerts", alerts=alerts)
    return HTMXBlockTemplate(
        template_str=template_str,
        re_target=request.query_params.get("alert-retarget", "#content") if request is not None else "#content",
        re_swap="beforeend",
    )
