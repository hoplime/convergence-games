from functools import cache

from fastapi import APIRouter
from fastui import FastUI
from fastui import components as c
from fastui.components.display import DisplayLookup, DisplayMode
from fastui.events import GoToEvent
from sqlmodel import select

from convergence_games.app.common import page
from convergence_games.app.dependencies import SessionDependency
from convergence_games.app.extra_models import PersonWithExtra
from convergence_games.db.models import Game, Genre, Person, System, TableAllocationRead, TimeSlot

router = APIRouter(prefix="/frontend/people")


@cache
def get_people_with_extra(session: SessionDependency):
    statement = select(Person)
    people = session.exec(statement).all()
    return [PersonWithExtra.model_validate(person) for person in people]


@cache
def get_person_lookup(session: SessionDependency):
    people = get_people_with_extra(session)
    return {person.id: person for person in people}


@router.get("/{id}", response_model_exclude_none=True)
async def api_person(*, session: SessionDependency, id: int) -> FastUI:
    person = get_person_lookup(session)[id]
    return page(
        c.Table(
            data=person.gmd_games,
            data_model=PersonWithExtra,
            columns=[
                DisplayLookup(field="title", title="Title", on_click=GoToEvent(url="/games/{id}")),
                DisplayLookup(field="times_available_string", title="Time Slots", mode=DisplayMode.auto),
            ],
        ),
        title=person.name,
    )
