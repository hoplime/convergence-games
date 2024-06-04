from functools import cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastui import FastUI
from fastui import components as c
from fastui.components.display import DisplayLookup, DisplayMode
from fastui.events import GoToEvent, PageEvent
from fastui.forms import SelectSearchResponse, fastui_form
from pydantic import BaseModel, Field
from sqlmodel import select

from convergence_games.app.common import page
from convergence_games.app.dependencies import SessionDependency
from convergence_games.app.extra_models import GameWithExtra, TableAllocationWithSlot
from convergence_games.db.extra_types import GameCrunch
from convergence_games.db.models import (
    Game,
    Genre,
    System,
    TimeSlot,
)

router = APIRouter(prefix="/frontend/games")


@cache
def get_games_with_extra(session: SessionDependency):
    statement = select(Game)
    games = session.exec(statement).all()
    return [GameWithExtra.model_validate(game) for game in games]


@cache
def get_game_lookup(session: SessionDependency):
    games = get_games_with_extra(session)
    return {game.id: game for game in games}


class GameFilterForm(BaseModel):
    # selected_genre_names: Annotated[list[str] | None, Field(title="Genres")]
    genre: Annotated[
        list[str] | None,
        Field(
            json_schema_extra={"search_url": "/frontend/games/genre_name_search", "placeholder": "Genre"},
            description="Genre",
        ),
    ]
    system: Annotated[
        list[str] | None,
        Field(
            json_schema_extra={"search_url": "/frontend/games/system_name_search", "placeholder": "System"},
            description="System",
        ),
    ]
    crunch: Annotated[
        list[GameCrunch] | None,
        Field(title="Crunch", json_schema_extra={"placeholder": "Crunch"}, description="Crunch level"),
    ]
    time_slot: Annotated[
        list[str] | None,
        Field(
            title="Time Slot",
            json_schema_extra={"search_url": "/frontend/games/time_slot_search", "placeholder": "Time Slot"},
            description="Time Slot",
        ),
    ]


@router.get("/genre_name_search", response_model=SelectSearchResponse)
async def genre_name_search(*, session: SessionDependency, q: str) -> SelectSearchResponse:
    genres = session.exec(select(Genre).order_by(Genre.name)).all()
    result = SelectSearchResponse(options=[{"value": genre.name, "label": genre.name} for genre in genres])
    return result


@router.get("/system_name_search", response_model=SelectSearchResponse)
async def system_name_search(*, session: SessionDependency, q: str) -> SelectSearchResponse:
    systems = session.exec(select(System).order_by(System.name)).all()
    result = SelectSearchResponse(options=[{"value": system.name, "label": system.name} for system in systems])
    return result


@router.get("/time_slot_search", response_model=SelectSearchResponse)
async def time_slot_search(*, session: SessionDependency, q: str) -> SelectSearchResponse:
    time_slots = session.exec(select(TimeSlot).order_by(TimeSlot.start_time)).all()
    result = SelectSearchResponse(
        options=[{"value": time_slot.name, "label": time_slot.name} for time_slot in time_slots]
    )
    return result


@router.get("", response_model_exclude_none=True)
async def get_games_view(
    *,
    session: SessionDependency,
    genre: list[str] | None | list[Literal[""]] = Query(None),
    system: list[str] | None | list[Literal[""]] = Query(None),
    crunch: list[GameCrunch] | None | list[Literal[""]] = Query(None),
    time_slot: list[str] | None | list[Literal[""]] = Query(None),
) -> FastUI:
    games = get_games_with_extra(session)

    if genre == [""]:
        genre = None
    if system == [""]:
        system = None
    if crunch == [""]:
        crunch = None
    if time_slot == [""]:
        time_slot = None

    filter_form_initial = {}
    if genre:
        games = [game for game in games if any(genre_name in game.genre_names for genre_name in genre)]
        filter_form_initial["genre"] = [{"value": genre_name, "label": genre_name} for genre_name in genre]
    if system:
        games = [game for game in games if any(system_name in game.system.name for system_name in system)]
        filter_form_initial["system"] = [{"value": system_name, "label": system_name} for system_name in system]
    if crunch:
        games = [game for game in games if game.crunch in crunch]
        filter_form_initial["crunch"] = crunch
    if time_slot:
        games = [
            game
            for game in games
            if any(
                time_slot_name in [ta.time_slot.name for ta in game.table_allocations] for time_slot_name in time_slot
            )
        ]
        filter_form_initial["time_slot"] = [
            {"value": time_slot_name, "label": time_slot_name} for time_slot_name in time_slot
        ]

    return page(
        c.Heading(text="Convergence Games"),
        c.ModelForm(
            model=GameFilterForm,
            display_mode="inline",
            submit_url=".",
            method="GOTO",
            submit_on_change=True,
            initial=filter_form_initial,
        ),
        c.Table(
            data=games,
            data_model=GameWithExtra,
            columns=[
                DisplayLookup(field="title", title="Name", on_click=GoToEvent(url="./{id}")),
                DisplayLookup(field="system_name", title="System"),
                DisplayLookup(field="game_master_name", title="GM", on_click=GoToEvent(url="/people/{game_master_id}")),
                DisplayLookup(field="genre_names_string", title="Genres"),
            ],
        ),
    )


@router.get("/{id}", response_model_exclude_none=True)
async def get_game_view(*, session: SessionDependency, id: int) -> FastUI:
    game = get_game_lookup(session)[id]
    return page(
        c.Heading(text=f"{game.system.name} | {', '.join(genre.name for genre in game.genres)}", level=3),
        c.Paragraph(text=f"{game.age_suitability} | {game.minimum_players} - {game.maximum_players} players"),
        c.Paragraph(text=f"{game.crunch} crunch | {game.narrativism} narrative | {game.tone} tone"),
        c.Paragraph(text=game.description),
        c.Div(
            components=[
                c.Text(text="Run by: "),
                c.Link(
                    components=[
                        c.Text(
                            text=game.gamemaster.name,
                        )
                    ],
                    on_click=GoToEvent(url=f"/people/{game.gamemaster.id}"),
                ),
            ]
        ),
        c.Heading(text="Sessions", level=2),
        c.Table(
            data=sorted(game.table_allocations, key=lambda ta: ta.time_slot.start_time),
            data_model=TableAllocationWithSlot,
            columns=[
                # DisplayLookup(field="slot_name", title="Time Slot"),
                DisplayLookup(
                    field="time_range",
                    title="Time",
                    on_click=PageEvent(name="modal-preference-display"),
                ),
                DisplayLookup(field="table_number", title="Table Number"),
            ],
        ),
        c.Modal(
            title="Sign Up",
            body=[
                c.Paragraph(text="TODO THE SIGN UP SCREEN"),
                c.Paragraph(
                    text="Form to select preference, and see and edit existing preferences for this session slot"
                ),
            ],
            open_trigger=PageEvent(name="modal-preference-display"),
        ),
        c.Button(
            text="Back to All Games",
            on_click=GoToEvent(url="/games"),
        ),
        title=game.title,
    )
