from functools import cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastui import FastUI
from fastui import components as c
from fastui.components.display import DisplayLookup
from fastui.events import GoToEvent
from fastui.forms import SelectSearchResponse, fastui_form
from pydantic import BaseModel, Field, computed_field
from sqlmodel import select

from convergence_games.app.common import page
from convergence_games.app.dependencies import SessionDependency
from convergence_games.db.extra_types import GameCrunch
from convergence_games.db.models import Game, GameRead, Genre, Person, System

router = APIRouter(prefix="/frontend/games")


class GameWithExtra(GameRead):
    genres: list[Genre] = []
    system: System
    gamemaster: Person

    @computed_field
    @property
    def genre_names(self) -> list[str]:
        return [genre.name for genre in self.genres]

    @computed_field
    @property
    def genre_names_string(self) -> str:
        return ", ".join(self.genre_names)


@cache
def get_games(session: SessionDependency):
    statement = select(Game)
    games = session.exec(statement).all()
    return [GameWithExtra.model_validate(game) for game in games]


@cache
def get_game_lookup(session: SessionDependency):
    games = get_games(session)
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


@router.get("/genre_name_search", response_model=SelectSearchResponse)
async def genre_name_search(*, session: SessionDependency, q: str) -> SelectSearchResponse:
    genres = session.exec(select(Genre)).all()
    result = SelectSearchResponse(options=[{"value": genre.name, "label": genre.name} for genre in genres])
    return result


@router.get("/system_name_search", response_model=SelectSearchResponse)
async def system_name_search(*, session: SessionDependency, q: str) -> SelectSearchResponse:
    systems = session.exec(select(System)).all()
    result = SelectSearchResponse(options=[{"value": system.name, "label": system.name} for system in systems])
    return result


@router.get("", response_model_exclude_none=True)
async def get_games_view(
    *,
    session: SessionDependency,
    genre: list[str] | None | list[Literal[""]] = Query(None),
    system: list[str] | None | list[Literal[""]] = Query(None),
    crunch: list[GameCrunch] | None | list[Literal[""]] = Query(None),
) -> FastUI:
    games = get_games(session)

    print(system)

    if genre == [""]:
        genre = None
    if system == [""]:
        system = None
    if crunch == [""]:
        crunch = None

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
                DisplayLookup(field="genre_names_string", title="Genres"),
            ],
        ),
    )


@router.get("/{id}", response_model_exclude_none=True)
async def get_game_view(*, session: SessionDependency, id: int) -> FastUI:
    game = get_game_lookup(session)[id]
    return page(
        c.Heading(text=game.title),
        c.Heading(text=f"{game.system.name} | ", level=3),
        c.Paragraph(text=f"Genres: {', '.join(genre.name for genre in game.genres)}"),
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
    )
