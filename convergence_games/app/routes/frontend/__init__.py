from typing import Annotated

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse
from sqlmodel import select

from convergence_games.app.dependencies import Session, User, get_user
from convergence_games.app.request_type import Request
from convergence_games.app.templates import templates
from convergence_games.db.models import Game, GameWithExtra, TableAllocation, TimeSlot
from convergence_games.db.session import Option

router = APIRouter(tags=["frontend"])


@router.get("/")
async def home(
    request: Request,
    user: User,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/home.html.jinja",
        context={"request": request, "user": user},
    )


@router.get("/games")
async def games(
    request: Request,
    user: User,
    genre: Annotated[list[int] | None, Query()] = None,
    system: Annotated[list[int] | None, Query()] = None,
    time_slot: Annotated[list[int] | None, Query()] = None,
) -> HTMLResponse:
    games = request.state.db.all_games

    # Determine filters
    if genre is not None:
        games = [game for game in games if any(genre_id in [g.id for g in game.genres] for genre_id in genre)]

    if system is not None:
        games = [game for game in games if game.system.id in system]

    if time_slot is not None:
        games = [
            game
            for game in games
            if any(
                time_slot_id in [table_allocation.time_slot.id for table_allocation in game.table_allocations]
                for time_slot_id in time_slot
            )
        ]

    genre_options = [
        Option(name=o.name, value=o.value, checked=o.value in genre if genre is not None else False)
        for o in request.state.db.genre_options
    ]
    system_options = [
        Option(name=o.name, value=o.value, checked=o.value in system if system is not None else False)
        for o in request.state.db.system_options
    ]
    time_slot_options = [
        Option(name=o.name, value=o.value, checked=o.value in time_slot if time_slot is not None else False)
        for o in request.state.db.time_slot_options
    ]

    push_url = request.url.path + ("?" + request.url.query if request.url.query else "")

    return templates.TemplateResponse(
        name="main/games.html.jinja",
        context={
            "games": games,
            "genre_options": genre_options,
            "system_options": system_options,
            "time_slot_options": time_slot_options,
            "request": request,
            "user": user,
        },
        headers={"HX-Push-Url": push_url},
    )


@router.get("/games/{game_id}")
async def game(
    request: Request,
    game_id: int,
    user: User,
) -> HTMLResponse:
    game = request.state.db.game_map[game_id]
    return templates.TemplateResponse(
        name="main/game.html.jinja",
        context={
            "game": game,
            "request": request,
            "user": user,
        },
    )


@router.get("/me")
async def login(
    request: Request,
    user: User,
) -> HTMLResponse:
    if user:
        return templates.TemplateResponse(
            name="main/profile.html.jinja",
            context={"request": request, "user": user},  # , block_name=hx_target
        )
    return templates.TemplateResponse(name="main/login.html.jinja", context={"request": request})


@router.post("/me")
async def login_post(
    request: Request,
    email: Annotated[str, Form()],
    session: Session,
) -> HTMLResponse:
    user = get_user(session, email)
    if user:
        return templates.TemplateResponse(
            name="main/profile.html.jinja",
            context={"request": request, "user": user},
            headers={"Set-Cookie": f"email={email}; SameSite=Lax"},
        )
    # TODO: Add error message
    return templates.TemplateResponse(name="main/login.html.jinja", context={"request": request})


@router.post("/logout")
async def logout(
    request: Request,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/login.html.jinja",
        context={"request": request, "user": None},
        headers={"Set-Cookie": "email=; Max-Age=0; SameSite=Lax"},
    )


@router.get("/preferences")
async def preferences(
    request: Request,
    user: User,
    session: Session,
    time_slot_id: Annotated[int, Query()] = 1,
) -> HTMLResponse:
    with session:
        time_slot = session.get(TimeSlot, time_slot_id)
        statement = (
            select(Game, TableAllocation)
            .where(TableAllocation.game_id == Game.id and TableAllocation.time_slot.id == time_slot_id)
            .group_by(Game.id)
            .order_by(Game.title)
        )
        games_and_table_allocations = session.exec(statement).all()
        games_and_table_allocations = [
            (GameWithExtra.model_validate(game), table_allocation)
            for game, table_allocation in games_and_table_allocations
        ]
        print(games_and_table_allocations)
    # {{ table_allocation.time_slot.start_time.strftime('%H:%M') }} -
    # {{ table_allocation.time_slot.end_time.strftime('%H:%M') }} on
    # {{ table_allocation.time_slot.start_time.strftime('%A') }}
    return templates.TemplateResponse(
        name="shared/partials/preferences.html.jinja",
        context={
            "request": request,
            "games_and_table_allocations": games_and_table_allocations,
            "time_slot_name": time_slot.start_time.strftime("%H:%M %A"),
        },
    )
