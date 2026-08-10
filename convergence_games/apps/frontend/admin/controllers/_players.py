from typing import Annotated

from litestar import Controller, get, put
from litestar.params import Body, RequestEncodingType
from litestar.response import Template
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from convergence_games.db.models import (
    Event,
    User,
    UserEventCompensationTransaction,
    UserEventD20Transaction,
    UserEventRole,
)
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.ocean import Sqid, sink, swim
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate
from convergence_games.lib.template import catalog

from .._common import SqidInt, user_can_manage_submissions


class PutEventPlayerTransactionForm(BaseModel):
    expected_latest_sqid: SqidInt | None = None
    delta: int


async def add_transaction_with_delta(
    table_type: type[UserEventD20Transaction] | type[UserEventCompensationTransaction],
    request: Request,
    event: Event,
    event_sqid: Sqid,
    user_sqid: Sqid,
    transaction: AsyncSession,
    data: Annotated[PutEventPlayerTransactionForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
) -> HTMXBlockTemplate:
    user_id = sink(user_sqid)
    delta = data.delta
    expected_latest_transaction_id = data.expected_latest_sqid

    player = (
        (
            await transaction.execute(
                select(User)
                .where(User.id == user_id)
                .options(
                    selectinload(
                        User.latest_d20_transaction
                        if table_type is UserEventD20Transaction
                        else User.latest_compensation_transaction
                    ),
                    with_loader_criteria(table_type, where_criteria=table_type.event_id == event.id),
                )
            )
        )
        .scalars()
        .one()
    )
    latest_transaction = (
        player.latest_d20_transaction
        if table_type is UserEventD20Transaction
        else player.latest_compensation_transaction
    )

    latest_transaction_id = None if latest_transaction is None else latest_transaction.id

    if expected_latest_transaction_id != latest_transaction_id:
        raise AlertError([Alert("alert-error", "You are out of sync with the database")])

    latest_current_balance = 0 if latest_transaction is None else latest_transaction.current_balance

    new_transaction_row = table_type(
        current_balance=latest_current_balance + delta,
        previous_balance=latest_current_balance,
        delta=delta,
        user_id=player.id,
        event_id=event.id,
        previous_transaction_id=latest_transaction_id,
    )
    transaction.add(new_transaction_row)
    await transaction.flush()
    await transaction.refresh(new_transaction_row)

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
    }

    @get(
        path="/event/{event_sqid:str}/manage-players",
    )
    async def get_event_manage_players(
        self,
        event: Event,
        request: Request,
        transaction: AsyncSession,
        permission: bool,
    ) -> Template:
        users = (
            (
                await transaction.execute(
                    select(User)
                    .options(
                        selectinload(User.latest_d20_transaction),
                        selectinload(User.latest_compensation_transaction),
                        selectinload(User.event_roles),
                        selectinload(User.logins),
                        with_loader_criteria(
                            UserEventCompensationTransaction, UserEventCompensationTransaction.event_id == event.id
                        ),
                        with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == event.id),
                        with_loader_criteria(
                            UserEventRole, (UserEventRole.event_id == event.id) | (UserEventRole.event_id.is_(None))
                        ),
                    )
                    .order_by(User.last_name, User.first_name)
                )
            )
            .scalars()
            .all()
        )
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
        transaction: AsyncSession,
        data: Annotated[PutEventPlayerTransactionForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        permission: bool,
    ) -> Template:
        return await add_transaction_with_delta(
            table_type=UserEventD20Transaction,
            request=request,
            event=event,
            event_sqid=event_sqid,
            user_sqid=user_sqid,
            transaction=transaction,
            data=data,
        )

    @put(
        path="/event/{event_sqid:str}/player/{user_sqid:str}/compensation",
    )
    async def put_player_compensation(
        self,
        request: Request,
        event: Event,
        event_sqid: Sqid,
        user_sqid: Sqid,
        transaction: AsyncSession,
        data: Annotated[PutEventPlayerTransactionForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
        permission: bool,
    ) -> Template:
        return await add_transaction_with_delta(
            table_type=UserEventCompensationTransaction,
            request=request,
            event=event,
            event_sqid=event_sqid,
            user_sqid=user_sqid,
            transaction=transaction,
            data=data,
        )
