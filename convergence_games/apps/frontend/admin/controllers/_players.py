from typing import Annotated

from litestar import Controller, get, put
from litestar.di import Provide
from litestar.params import Body, RequestEncodingType
from litestar.response import Template
from pydantic import BaseModel

from convergence_games.db.models import Event, UserEventCompensationTransaction, UserEventD20Transaction
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate
from convergence_games.lib.template import catalog

from .._common import SqidInt, user_can_manage_submissions
from ..services import PlayerService, provide_player_service


class PutEventPlayerTransactionForm(BaseModel):
    expected_latest_sqid: SqidInt | None = None
    delta: int


def _render_balance_delta(
    request: Request,
    table_type: type[UserEventD20Transaction] | type[UserEventCompensationTransaction],
    new_transaction_row: UserEventD20Transaction | UserEventCompensationTransaction,
    event_sqid: Sqid,
    user_sqid: Sqid,
) -> HTMXBlockTemplate:
    template_str = catalog.render(
        "UserManageDelta",
        current_value=new_transaction_row.current_balance,
        expected_latest_sqid=swim(new_transaction_row),
        endpoint=f"/event/{event_sqid}/player/{user_sqid}/{'d20s' if table_type is UserEventD20Transaction else 'compensation'}",
    )
    return HTMXBlockTemplate(template_str=template_str, block_name=request.htmx.target)


class PlayersController(Controller):
    guards = [user_guard]
    dependencies = {
        "event": event_with(),
        "permission": permission_check(user_can_manage_submissions),
        "player_service": Provide(provide_player_service),
    }

    @get(
        path="/event/{event_sqid:str}/manage-players",
    )
    async def get_event_manage_players(
        self,
        event: Event,
        request: Request,
        player_service: PlayerService,
        permission: bool,
    ) -> Template:
        users = await player_service.list_players(event.id)
        return HTMXBlockTemplate(
            template_name="pages/event_manage_players.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "users": users,
            },
        )

    @put(
        path="/event/{event_sqid:str}/player/{user_sqid:str}/d20s",
    )
    async def put_player_d20s(
        self,
        request: Request,
        event: Event,
        event_sqid: Sqid,
        user_sqid: Sqid,
        player_service: PlayerService,
        data: Annotated[PutEventPlayerTransactionForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        permission: bool,
    ) -> Template:
        new_transaction_row = await player_service.add_balance_transaction(
            UserEventD20Transaction,
            event_id=event.id,
            user_id=sink(user_sqid),
            delta=data.delta,
            expected_latest_transaction_id=data.expected_latest_sqid,
        )
        return _render_balance_delta(request, UserEventD20Transaction, new_transaction_row, event_sqid, user_sqid)

    @put(
        path="/event/{event_sqid:str}/player/{user_sqid:str}/compensation",
    )
    async def put_player_compensation(
        self,
        request: Request,
        event: Event,
        event_sqid: Sqid,
        user_sqid: Sqid,
        player_service: PlayerService,
        data: Annotated[PutEventPlayerTransactionForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        permission: bool,
    ) -> Template:
        new_transaction_row = await player_service.add_balance_transaction(
            UserEventCompensationTransaction,
            event_id=event.id,
            user_id=sink(user_sqid),
            delta=data.delta,
            expected_latest_transaction_id=data.expected_latest_sqid,
        )
        return _render_balance_delta(
            request, UserEventCompensationTransaction, new_transaction_row, event_sqid, user_sqid
        )
