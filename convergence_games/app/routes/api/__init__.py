from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, create_model
from sqlmodel import SQLModel, inspect, select

from convergence_games.app.dependencies import Auth, EngineDependency, Session
from convergence_games.app.routes.api.models import boilerplates
from convergence_games.app.shared import do_allocation, get_compensation
from convergence_games.db.models import AllocationResult
from convergence_games.settings import SETTINGS

router = APIRouter(prefix="/api", dependencies=[Auth])


@router.get("/settings", tags=["admin"])
async def get_settings() -> dict[str, Any]:
    return SETTINGS.model_dump()


for boilerplate in boilerplates:

    def bind_routes(
        table_type: type[SQLModel] = boilerplate.table,
        read_type: type[SQLModel] = boilerplate.read or boilerplate.table,
        extra_type: type[SQLModel] | None = boilerplate.extra or boilerplate.read or boilerplate.table,
        create_type: type[SQLModel] | None = boilerplate.create,
        update_type: type[SQLModel] | None = boilerplate.update,
    ) -> None:
        table_name = table_type.__name__.lower()

        primary_keys = inspect(table_type).primary_key
        primary_key_names = [pk.name for pk in primary_keys]
        primary_key_path = "/".join([f"{{{pk_name}}}" for pk_name in primary_key_names])
        id_args_model: BaseModel = create_model(
            f"IdArgs{table_type.__name__}",
            __config__=ConfigDict(populate_by_name=True),
            **{pk_name: (int, Path(alias=pk_name)) for pk_name in primary_key_names},
        )

        @router.get(f"/{table_name}", name=f"Get all {table_name}s", tags=[table_name])
        async def get_all(session: Session) -> list[extra_type]:
            with session:
                statement = select(table_type)
                result = session.exec(statement).all()
                return [extra_type.model_validate(row) for row in result]

        @router.get(f"/{table_name}/{primary_key_path}", name=f"Get {table_name} by id", tags=[table_name])
        async def get_by_id(session: Session, id_args=Depends(id_args_model)) -> extra_type:
            with session:
                result = session.get(table_type, id_args.model_dump())
                if result is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{table_name} not found")

                return extra_type.model_validate(result)

        if create_type is not None:

            @router.post(f"/{table_name}", name=f"Create {table_name}", tags=[table_name])
            async def create(session: Session, item: create_type) -> extra_type:
                with session:
                    db_item = table_type.model_validate(item)
                    session.add(db_item)
                    session.commit()
                    session.refresh(db_item)
                    return extra_type.model_validate(db_item)

        if update_type is not None:

            @router.patch(f"/{table_name}/{primary_key_path}", name=f"Update {table_name}", tags=[table_name])
            async def update(
                session: Session, item: update_type, id_args: BaseModel = Depends(id_args_model)
            ) -> extra_type:
                with session:
                    result = session.get(table_type, id_args.model_dump())
                    if result is None:
                        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{table_name} not found")

                    update_data = item.model_dump(exclude_unset=True)
                    result.sqlmodel_update(update_data)
                    session.add(result)
                    session.commit()
                    session.refresh(result)
                    return extra_type.model_validate(result)

    bind_routes()


@router.post("/log/{time_slot_id}", tags=["admin"])
async def log(
    time_slot_id: int,
    force_override: Annotated[bool, Query()] = False,
) -> HTMLResponse:
    print(f"Logging {time_slot_id=} with {force_override=}")
    return "<div>Logged</div>"


@router.post("/allocate_draft/{time_slot_id}", tags=["admin"])
async def allocate_draft(
    time_slot_id: int,
    engine: EngineDependency,
    force_override: Annotated[bool, Query()] = False,
) -> list[AllocationResult]:
    return do_allocation(time_slot_id, engine, force_override)


@router.get("/compensation/{time_slot_id}", tags=["admin"])
async def compensation(
    time_slot_id: int,
    engine: EngineDependency,
) -> Any:
    return get_compensation(time_slot_id, engine)
