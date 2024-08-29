from fastapi import HTTPException, status
from sqlmodel import Session, select

from convergence_games.algorithm.game_allocator import GameAllocator
from convergence_games.app.dependencies import EngineDependency
from convergence_games.db.models import AllocationResult, TableAllocation


def do_allocation(time_slot_id: int, engine: EngineDependency, force_override: bool) -> list[AllocationResult]:
    game_allocator = GameAllocator(engine, time_slot_id)
    result = game_allocator.allocate(n_trials=50)  # TODO: Boost for final event
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
