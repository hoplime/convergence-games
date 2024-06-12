from typing import Annotated

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from convergence_games.app.dependencies import HxTarget
from convergence_games.app.request_type import Request
from convergence_games.app.templates import templates
from convergence_games.db.session import Option

router = APIRouter(tags=["frontend"])


@router.get("/games")
async def games(
    request: Request,
    hx_target: HxTarget,
    genre: Annotated[list[int] | None, Query()] = None,
    system: Annotated[list[int] | None, Query()] = None,
) -> HTMLResponse:
    games = request.state.db.all_games

    if genre is not None:
        games = [game for game in games if any(genre_id in [g.id for g in game.genres] for genre_id in genre)]

    if system is not None:
        games = [game for game in games if game.system.id in system]

    push_url = request.url.path + ("?" + request.url.query if request.url.query else "")
    genre_options = [
        Option(name=o.name, value=o.value, checked=o.value in genre if genre is not None else False)
        for o in request.state.db.genre_options
    ]
    system_options = [
        Option(name=o.name, value=o.value, checked=o.value in system if system is not None else False)
        for o in request.state.db.system_options
    ]
    print(system_options)

    return templates.TemplateResponse(
        name="main/games.html.jinja",
        context={
            "games": games,
            "genre_options": genre_options,
            "system_options": system_options,
            "request": request,
        },
        block_name=hx_target,
        headers={"HX-Push-Url": push_url},
    )


@router.get("/games/{game_id}")
async def game(
    request: Request,
    target_name: HxTarget,
    game_id: int,
) -> HTMLResponse:
    game = request.state.db.game_map[game_id]
    return templates.TemplateResponse(
        name="main/game.html.jinja", context={"game": game, "request": request}, block_name=target_name
    )
