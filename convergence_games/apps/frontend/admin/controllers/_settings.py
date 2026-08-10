import zoneinfo
from datetime import datetime, timezone
from typing import Annotated, Any

from litestar import Controller, get, put
from litestar.params import Body, RequestEncodingType
from litestar.response import Response, Template
from litestar.status_codes import HTTP_200_OK
from pydantic import BaseModel, BeforeValidator
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Event
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.ocean import swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from .._common import user_can_manage_submissions


def _empty_to_none(v: Any) -> datetime | None:
    if v == "" or v is None:
        return None
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return v


EmptyToNone = BeforeValidator(_empty_to_none)


class PutEventSettingsForm(BaseModel):
    submissions_open_at: Annotated[datetime | None, EmptyToNone] = None
    submissions_close_at: Annotated[datetime | None, EmptyToNone] = None
    editing_close_at: Annotated[datetime | None, EmptyToNone] = None
    preferences_open_at: Annotated[datetime | None, EmptyToNone] = None
    planner_open_at: Annotated[datetime | None, EmptyToNone] = None


class SettingsController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(),
        "permission": permission_check(user_can_manage_submissions),
    }

    @get(
        path="/event/{event_sqid:str}/manage-settings",
    )
    async def get_event_manage_settings(
        self,
        request: Request,
        event: Event,
        permission: bool,
    ) -> Template:
        tz = zoneinfo.ZoneInfo(event.timezone)
        return HTMXBlockTemplate(
            template_name="pages/event_manage_settings.html.jinja",
            block_name=request.htmx.target,
            context={"event": event, "tz": tz},
        )

    @put(
        path="/event/{event_sqid:str}/manage-settings",
    )
    async def put_event_manage_settings(
        self,
        request: Request,
        transaction: AsyncSession,
        event: Event,
        permission: bool,
        data: Annotated[PutEventSettingsForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Response[str]:
        tz = zoneinfo.ZoneInfo(event.timezone)

        def to_utc(naive: datetime | None) -> datetime | None:
            if naive is None:
                return None
            return naive.replace(tzinfo=tz).astimezone(timezone.utc)

        event.submissions_open_at = to_utc(data.submissions_open_at)
        event.submissions_close_at = to_utc(data.submissions_close_at)
        event.editing_close_at = to_utc(data.editing_close_at)
        event.preferences_open_at = to_utc(data.preferences_open_at)
        event.planner_open_at = to_utc(data.planner_open_at)
        transaction.add(event)

        return Response(
            content="",
            status_code=HTTP_200_OK,
            headers={"HX-Redirect": f"/event/{swim(event)}/manage-settings"},
        )
