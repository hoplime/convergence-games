from typing import Literal

from fastapi import HTTPException, status
from sqlmodel import Session, select

from convergence_games.algorithm.game_allocator import (
    CurrentGameAllocation,
    GameAllocator,
    Group,
    table_allocation_id_t,
)
from convergence_games.app.dependencies import EngineDependency
from convergence_games.db.models import (
    AllocationResult,
    CommittedAllocationResult,
    Compensation,
    TableAllocation,
    TableAllocationResultView,
    TableAllocationWithExtra,
)


def get_compensation(
    time_slot_id: int,
    engine: EngineDependency,
    result_table: Literal["allocation_results", "committed_allocation_results"] = "committed_allocation_results",
) -> list[Compensation]:
    game_allocator = GameAllocator(engine, time_slot_id)
    result: dict[table_allocation_id_t, CurrentGameAllocation] = {}
    with Session(engine) as session:
        # Get overflow table
        overflow_table_allocation_id = session.exec(
            select(TableAllocation.id).filter(
                (TableAllocation.game_id == 0) & (TableAllocation.time_slot_id == time_slot_id)
            )
        ).first()
        preference_overrides = {overflow_table_allocation_id: 0.5}

        table_allocations = session.exec(
            select(TableAllocation).where(TableAllocation.time_slot_id == time_slot_id)
        ).all()
        table_allocations_with_results = [
            TableAllocationResultView.model_validate(table_allocation) for table_allocation in table_allocations
        ]
        table_allocations_with_extra = [
            TableAllocationWithExtra.model_validate(table_allocation) for table_allocation in table_allocations
        ]

        for table_allocation in table_allocations_with_results:
            allocation_result: list[AllocationResult] | list[CommittedAllocationResult] = getattr(
                table_allocation, result_table
            )
            groups = [r.adventuring_group for r in allocation_result]
            game_master_group = next(
                (g for g in groups if table_allocation.game.gamemaster_id in (member.id for member in g.members)),
                None,
            )
            if game_master_group is not None:
                groups.remove(game_master_group)

            result[table_allocation.id] = CurrentGameAllocation(
                table_allocation=table_allocation,
                game_master=None
                if game_master_group is None
                else Group.from_adventuring_group(
                    game_master_group,
                    table_allocations=table_allocations_with_extra,
                    preference_overrides=preference_overrides,
                ),
                groups=[
                    Group.from_adventuring_group(
                        group,
                        table_allocations=table_allocations_with_extra,
                        preference_overrides=preference_overrides,
                    )
                    for group in groups
                ],
            )
    compensation_result = game_allocator.get_compensation_and_d20s(result)
    compensations: list[Compensation] = []
    for person_id, (compensation_value, d20s_spent) in compensation_result.as_combined.items():
        compensations.append(
            Compensation(
                person_id=person_id,
                time_slot_id=time_slot_id,
                compensation_delta=compensation_value,
                golden_d20_delta=-d20s_spent,
                applied=False,
            )
        )
    return compensations


def do_allocation(time_slot_id: int, engine: EngineDependency, force_override: bool) -> list[AllocationResult]:
    game_allocator = GameAllocator(engine, time_slot_id)
    result = game_allocator.allocate(n_trials=1000)  # TODO: Boost for final event
    allocation_results = [x for r in result.values() for x in r.to_serializable()]
    with Session(engine) as session:
        # Check if there already exists any allocation results for the given time slot
        existing_results = session.exec(
            select(AllocationResult)
            .join(TableAllocation, AllocationResult.table_allocation_id == TableAllocation.id)
            .where(TableAllocation.time_slot_id == time_slot_id)
        ).all()
        if existing_results and not force_override:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Allocation results already exist for time slot {time_slot_id}",
            )

        # Delete existing allocation results for the given time slot
        for existing_result in existing_results:
            session.delete(existing_result)

        # Add new allocation results
        session.add_all(allocation_results)
        session.commit()
        for result in allocation_results:
            session.refresh(result)
    return allocation_results
