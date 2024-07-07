from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Iterator, Literal

from fastapi import APIRouter, Form, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, BeforeValidator, ConfigDict, RootModel
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlmodel import select

from convergence_games.app.dependencies import HxTarget, Session, User, get_user
from convergence_games.app.request_type import Request
from convergence_games.app.templates import templates
from convergence_games.db.extra_types import DEFINED_AGE_SUITABILITIES, DEFINED_CONTENT_WARNINGS, GameCrunch, GameTone
from convergence_games.db.models import Game, GameWithExtra, Person, SessionPreference, TableAllocation, TimeSlot
from convergence_games.db.session import Option

router = APIRouter(tags=["frontend"], include_in_schema=False)


# region Main Pages
@router.get("/")
async def home(
    request: Request,
    user: User,
    hx_target: HxTarget,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/home.html.jinja",
        context={"request": request, "user": user},
        block_name=hx_target,
    )


@router.get("/games")
async def games(
    request: Request,
    user: User,
    hx_target: HxTarget,
    genre: Annotated[list[int] | None, Query()] = None,
    system: Annotated[list[int] | None, Query()] = None,
    time_slot: Annotated[list[int] | None, Query()] = None,
    crunch: Annotated[list[GameCrunch] | None, Query()] = None,
    tone: Annotated[list[GameTone] | None, Query()] = None,
    blocked_content_warnings: Annotated[list[str] | None, Query()] = None,
    age_suitability: Annotated[list[str] | None, Query()] = None,
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

    if crunch is not None:
        games = [game for game in games if game.crunch in crunch]

    if tone is not None:
        games = [game for game in games if game.tone in tone]

    if blocked_content_warnings is not None:
        games = [
            game
            for game in games
            if not any(
                content_warning in [cw.name for cw in game.content_warnings]
                for content_warning in blocked_content_warnings
            )
        ]

    if age_suitability is not None:
        games = [game for game in games if game.age_suitability in age_suitability]

    # Determine dropdown options
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
    crunch_options = [
        Option(name=e.value, value=e.value, checked=e.value in crunch if crunch is not None else False)
        for e in GameCrunch
    ]
    tone_options = [
        Option(name=e.value, value=e.value, checked=e.value in tone if tone is not None else False) for e in GameTone
    ]
    blocked_content_warning_options = [
        Option(
            name=w,
            value=w,
            checked=w in blocked_content_warnings if blocked_content_warnings is not None else False,
        )
        for w in DEFINED_CONTENT_WARNINGS
    ]
    age_suitability_options = [
        Option(
            name=a,
            value=a,
            checked=a in tone if tone is not None else False,
        )
        for a in DEFINED_AGE_SUITABILITIES
    ]

    push_url = request.url.path + ("?" + request.url.query if request.url.query else "")

    return templates.TemplateResponse(
        name="main/games.html.jinja",
        context={
            "games": games,
            "genre_options": genre_options,
            "system_options": system_options,
            "time_slot_options": time_slot_options,
            "crunch_options": crunch_options,
            "tone_options": tone_options,
            "blocked_content_warning_options": blocked_content_warning_options,
            "age_suitability_options": age_suitability_options,
            "request": request,
            "user": user,
        },
        headers={"HX-Push-Url": push_url},
        block_name=hx_target,
    )


@router.get("/games/{game_id}")
async def game(
    request: Request,
    user: User,
    hx_target: HxTarget,
    game_id: int,
) -> HTMLResponse:
    if game_id not in request.state.db.game_map:
        return HTMLResponse(status_code=404)
    game = request.state.db.game_map[game_id]
    return templates.TemplateResponse(
        name="main/game.html.jinja",
        context={
            "game": game,
            "request": request,
            "user": user,
        },
        block_name=hx_target,
    )


@router.get("/me")
async def me(
    request: Request,
    user: User,
    hx_target: HxTarget,
) -> HTMLResponse:
    if user:
        return templates.TemplateResponse(
            name="main/profile.html.jinja",
            context={"request": request, "user": user},
            block_name=hx_target,
        )
    return templates.TemplateResponse(
        name="main/login.html.jinja",
        context={"request": request},
        headers={"Set-Cookie": "email=; Max-Age=0; SameSite=Lax"},
        block_name=hx_target,
    )


@router.get("/login")
async def login(
    request: Request,
    hx_target: HxTarget,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/login.html.jinja",
        context={"request": request},
        block_name=hx_target,
    )


@router.post("/login")
async def login_post(
    request: Request,
    hx_target: HxTarget,
    email: Annotated[str, Form()],
    session: Session,
) -> HTMLResponse:
    user = get_user(session, email.lower())
    if user is None:
        return templates.TemplateResponse(
            name="main/signup.html.jinja",
            context={
                "request": request,
                "email": email,
                "alerts": [Alert("Email not found, going to sign up", "warning")],
            },
            block_name=hx_target,
        )
    else:
        return templates.TemplateResponse(
            name="main/profile.html.jinja",
            context={"request": request, "user": user},
            headers={"Set-Cookie": f"email={email}; SameSite=Lax"},
        )


@router.get("/signup")
async def signup(
    request: Request,
    hx_target: HxTarget,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/signup.html.jinja",
        context={"request": request},
        block_name=hx_target,
    )


@dataclass
class Alert:
    message: str
    type: Literal["info", "success", "warning", "error"] = "info"

    @property
    def alert_class(self) -> str:
        return f"alert-{self.type}"


@router.post("/signup")
async def signup_post(
    request: Request,
    hx_target: HxTarget,
    email: Annotated[str, Form()],
    name: Annotated[str, Form()],
    session: Session,
) -> HTMLResponse:
    with session:
        user = Person(email=email, name=name)
        session.add(user)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            return templates.TemplateResponse(
                name="main/signup.html.jinja",
                context={
                    "request": request,
                    "email": email,
                    "name": name,
                    "alerts": [Alert("Email already in use, please login instead", "error")],
                },
                block_name=hx_target,
            )
        session.refresh(user)
    return templates.TemplateResponse(
        name="main/profile.html.jinja",
        context={"request": request, "user": user},
        headers={"Set-Cookie": f"email={email}; SameSite=Lax"},
        block_name=hx_target,
    )


@router.post("/logout")
async def logout_post(
    request: Request,
    hx_target: HxTarget,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="main/login.html.jinja",
        context={"request": request, "user": None},
        headers={"Set-Cookie": "email=; Max-Age=0; SameSite=Lax"},
        block_name=hx_target,
    )


# endregion


# region Partials
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
            select(Game, TableAllocation, SessionPreference)
            .join(
                TableAllocation,
                (TableAllocation.game_id == Game.id) & (TableAllocation.time_slot_id == time_slot_id),
            )
            .outerjoin(
                SessionPreference,
                (SessionPreference.person_id == user.id)
                & (SessionPreference.table_allocation_id == TableAllocation.id),
            )
            .group_by(Game.id)
            .order_by(Game.title)
            # .where(SessionPreference.person_id == user.id)
        )
        preferences_data = session.exec(statement).all()
        preferences_data = [
            (
                GameWithExtra.model_validate(game),
                table_allocation,
                str(session_preference.preference if session_preference is not None else 3),
            )
            for game, table_allocation, session_preference in preferences_data
        ]
    return templates.TemplateResponse(
        name="shared/partials/preferences.html.jinja",
        context={
            "request": request,
            "user": user,
            "preferences_data": preferences_data,
            "time_slot": time_slot,
        },
    )


class RatingValue(Enum):
    ZERO = "0"
    ONE = "1"
    TWO = "2"
    THREE = "3"
    FOUR = "4"
    FIVE = "5"
    D20 = "20"

    def numeric(self) -> int:
        return int(self.value)


RatingTableAllocationKey = Annotated[int, BeforeValidator(lambda rating_x: int(rating_x.removeprefix("rating-")))]


class RatingForm(RootModel, Mapping[int, RatingValue]):
    root: dict[RatingTableAllocationKey, RatingValue]

    def __len__(self) -> int:
        return len(self.root)

    def __getitem__(self, key: int) -> RatingValue:
        return self.root[key]

    def __iter__(self) -> Iterator[int]:
        return iter(self.root)


@router.post("/preferences")
async def preferences_post(
    request: Request,
    user: User,
    session: Session,
    time_slot_id: Annotated[int, Query()],
    # form: Annotated[RatingForm, Form()],
    # time_slot_id: Annotated[int, Form()],
    # game_ids: Annotated[list[int], Form()],
) -> HTMLResponse:
    form_data = await request.form()
    table_allocation_ratings = RatingForm.model_validate(form_data)
    person_id = user.id
    with session:
        session_preferences: list[SessionPreference] = []
        for table_allocation_id, rating in table_allocation_ratings.items():
            session_preference = SessionPreference(
                preference=rating.numeric(), person_id=person_id, table_allocation_id=table_allocation_id
            )

            session_preferences.append(session_preference)
        statement = sqlite_upsert(SessionPreference).values([pref.model_dump() for pref in session_preferences])
        statement = statement.on_conflict_do_update(
            set_={"preference": statement.excluded.preference},
        )
        session.exec(statement)
        session.commit()
    return await preferences(request, user, session, time_slot_id)


@router.get("/edit_profile")
async def user_edit(
    request: Request,
    user: User,
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="shared/partials/profile_info_edit.html.jinja",
        context={"request": request, "user": user},
    )


@router.put("/edit_profile")
async def user_edit_post(
    request: Request,
    user: User,
    session: Session,
    name: Annotated[str, Form()],
    golden_d20s: Annotated[int, Form()],
) -> HTMLResponse:
    with session:
        user.name = name
        user.golden_d20s = golden_d20s
        session.add(user)
        session.commit()
        session.refresh(user)
    return templates.TemplateResponse(
        name="shared/partials/profile_info.html.jinja",
        context={"request": request, "user": user},
    )


# endregion
