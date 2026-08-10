from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, with_loader_criteria

from convergence_games.db.models import (
    User,
    UserEventCompensationTransaction,
    UserEventD20Transaction,
    UserEventRole,
)
from convergence_games.lib.alerts import Alert, AlertError


class PlayerService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_players(self, event_id: int) -> Sequence[User]:
        return (
            (
                await self._session.execute(
                    select(User)
                    .options(
                        selectinload(User.latest_d20_transaction),
                        selectinload(User.latest_compensation_transaction),
                        selectinload(User.event_roles),
                        selectinload(User.logins),
                        with_loader_criteria(
                            UserEventCompensationTransaction,
                            UserEventCompensationTransaction.event_id == event_id,
                        ),
                        with_loader_criteria(UserEventD20Transaction, UserEventD20Transaction.event_id == event_id),
                        with_loader_criteria(
                            UserEventRole, (UserEventRole.event_id == event_id) | (UserEventRole.event_id.is_(None))
                        ),
                    )
                    .order_by(User.last_name, User.first_name)
                )
            )
            .scalars()
            .all()
        )

    async def add_balance_transaction[T: (UserEventD20Transaction, UserEventCompensationTransaction)](
        self,
        table_type: type[T],
        *,
        event_id: int,
        user_id: int,
        delta: int,
        expected_latest_transaction_id: int | None,
    ) -> T:
        player = (
            (
                await self._session.execute(
                    select(User)
                    .where(User.id == user_id)
                    .options(
                        selectinload(
                            User.latest_d20_transaction
                            if table_type is UserEventD20Transaction
                            else User.latest_compensation_transaction
                        ),
                        with_loader_criteria(table_type, where_criteria=table_type.event_id == event_id),
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
            event_id=event_id,
            previous_transaction_id=latest_transaction_id,
        )
        self._session.add(new_transaction_row)
        await self._session.flush()
        await self._session.refresh(new_transaction_row)

        return new_transaction_row


async def provide_player_service(transaction: AsyncSession) -> PlayerService:
    return PlayerService(transaction)
