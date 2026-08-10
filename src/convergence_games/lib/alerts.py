from dataclasses import dataclass
from typing import Literal, final


@dataclass
class Alert:
    alert_class: Literal["alert-success", "alert-info", "alert-warning", "alert-error"]
    message: str


@final
class AlertError(Exception):
    def __init__(self, alerts: list[Alert], redirect_text: str | None = None, redirect_url: str | None = None):
        super().__init__()
        self.alerts = alerts
        self.redirect_text = redirect_text
        self.redirect_url = redirect_url
