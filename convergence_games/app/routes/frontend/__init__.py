import random
import string
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Iterator, Literal

from fastapi import APIRouter, Form, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BeforeValidator, RootModel
from sqlalchemy import func
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert
from sqlmodel import exists, select

from convergence_games.app.dependencies import (
    AuthWithHandler,
    EngineDependency,
    HxTarget,
    Session,
    User,
    get_user,
)
from convergence_games.app.request_type import Request
from convergence_games.app.shared.do_allocation import do_allocation, get_compensation
from convergence_games.app.templates import templates
from convergence_games.db.extra_types import (
    DEFINED_AGE_SUITABILITIES,
    DEFINED_CONTENT_WARNINGS,
    GameCrunch,
    GameTone,
)
from convergence_games.db.models import (
    AdventuringGroup,
    AdventuringGroupWithExtra,
    AllocationResult,
    CommittedAllocationResult,
    Compensation,
    CompensationWithExtra,
    Game,
    GameWithExtra,
    Person,
    PersonAdventuringGroupLink,
    PersonUpdate,
    PersonWithExtra,
    SessionPreference,
    Table,
    TableAllocation,
    TableAllocationResultView,
    TimeSlot,
)
from convergence_games.db.session import Option

router = APIRouter(tags=["frontend"], include_in_schema=False)


def alerts_template_response(alerts: list["Alert"], request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        name="shared/partials/toast_alerts.html.jinja",
        context={
            "request": request,
            "alerts": alerts,
        },
        headers={"HX-Retarget": "#content", "HX-Reswap": "beforeend"},
    )


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
    games = [game for game in request.state.db.all_games if not game.hidden]

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

    push_url = "/games" + ("?" + request.url.query if request.url.query else "")

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
            headers={"Set-Cookie": f"email={email}; SameSite=Lax", "HX-Redirect": "/me"},
            block_name=hx_target,
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

    @property
    def text_class(self) -> str:
        return f"text-{self.type}"


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
                name="main/login.html.jinja",
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
        headers={"Set-Cookie": f"email={email}; SameSite=Lax", "HX-Redirect": "/me"},
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
        headers={"Set-Cookie": "email=; Max-Age=0; SameSite=Lax", "HX-Redirect": "/me"},
        block_name=hx_target,
    )


def create_initial_adventuring_group(
    session: Session, person: Person, time_slot_id: int, checked_in: bool = False
) -> None:
    for trial in range(100):
        random_code = get_random_group_code(seed=hash(person.email + str(trial)))
        existing_group = session.exec(
            select(AdventuringGroup).where(
                (AdventuringGroup.name == random_code) & (AdventuringGroup.time_slot_id == time_slot_id)
            )
        ).first()
        if existing_group is None:
            break

    adventuring_group = AdventuringGroup(
        name=random_code,
        members=[person],
        time_slot_id=time_slot_id,
        checked_in=checked_in,
    )
    session.add(adventuring_group)
    session.commit()
    session.refresh(adventuring_group)
    return adventuring_group


def get_random_group_code(seed: int = 0) -> str:
    random.seed(seed)
    return "".join(random.choices(string.ascii_uppercase, k=6))


def get_adventuring_group_from_user_and_time_slot_id(
    session: Session, user_id: int, time_slot_id: int
) -> AdventuringGroup:
    person = session.get(Person, user_id)
    person_with_extra = PersonWithExtra.model_validate(person)
    adventuring_group = next(
        (group for group in person_with_extra.adventuring_groups if group.time_slot_id == time_slot_id),
        None,
    )

    if adventuring_group is None:
        adventuring_group = create_initial_adventuring_group(session, person, time_slot_id, checked_in=False)

    return adventuring_group


@router.get("/adventuring_party_edit_code")
async def adventuring_party_edit_code(
    request: Request,
    adventuring_group_id: Annotated[int, Query()],
    adventuring_group_name: Annotated[str, Query()],
    time_slot_id: Annotated[int, Query()],
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="shared/partials/adventuring_party_edit_code.html.jinja",
        context={
            "request": request,
            "adventuring_group_id": adventuring_group_id,
            "adventuring_group_name": adventuring_group_name,
            "time_slot_id": time_slot_id,
        },
    )


@router.put("/change_group_name")
async def change_group_name(
    request: Request,
    user: User,
    session: Session,
    adventuring_group_id: Annotated[int, Query()],
    host_code: Annotated[str, Form()],
    hx_target: HxTarget,
) -> HTMLResponse:
    with session:
        group = session.get(AdventuringGroup, adventuring_group_id)
        if user.id not in {member.id for member in group.members}:
            return alerts_template_response([Alert("You are not in this party", "error")], request)

        group.name = host_code.upper()
        session.add(group)
        try:
            session.commit()
        except Exception as e:
            session.rollback()
            return alerts_template_response([Alert("Code already in use, did you mean to join?", "error")], request)
        session.refresh(group)
    return await schedule(request, user, session, hx_target, group.time_slot_id)


def remove_person_from_group(session: Session, current_group: AdventuringGroup, person_id: int) -> None:
    print("Removing", person_id, "from", current_group.id)
    current_group.members = [member for member in current_group.members if member.id != person_id]
    if not current_group.members:
        print("DELETING OLD GROUP")
        for session_preference in current_group.session_preferences:
            session.delete(session_preference)
        session.commit()  # TODO: There's got to be a nicer way (cascade delete?) but for now delete each thing in turn
        for allocation_result in current_group.allocation_results:
            session.delete(allocation_result)
        session.commit()
        for committed_allocation_result in current_group.committed_allocation_results:
            session.delete(committed_allocation_result)
        session.commit()
        session.delete(current_group)
    else:
        session.add(current_group)


@router.put("/join_group")
async def join_group(
    request: Request,
    user: User,
    session: Session,
    current_adventuring_group_id: Annotated[int, Query()],
    join_code: Annotated[str, Form()],
    hx_target: HxTarget,
) -> HTMLResponse:
    with session:
        if (alerts := maybe_alerts_if_group_locked(request, session, current_adventuring_group_id)) is not None:
            return alerts

        person = session.get(Person, user.id)
        current_group = session.get(AdventuringGroup, current_adventuring_group_id)

        if current_group.name == join_code.upper():
            return alerts_template_response([Alert("You are already in this party", "warning")], request)

        new_group = session.exec(
            select(AdventuringGroup).where(
                (AdventuringGroup.name == join_code.upper())
                & (current_group.time_slot_id == AdventuringGroup.time_slot_id)
            )
        ).first()

        if new_group is None:
            return alerts_template_response([Alert("Party not found", "error")], request)

        if (alerts := maybe_alerts_if_group_locked(request, session, new_group.id)) is not None:
            return alerts

        # Group limits!
        if len(new_group.members) >= 3:
            return alerts_template_response([Alert("Party is full (max 3 members)", "error")], request)

        # Remove from current group
        remove_person_from_group(session, current_group, person.id)

        new_group.members.append(person)
        time_slot_id = new_group.time_slot_id
        session.add(new_group)
        session.commit()

        return await schedule(request, user, session, hx_target, time_slot_id)


@router.put("/leave_group")
async def leave_group(
    request: Request,
    user: User,
    session: Session,
    adventuring_group_id: Annotated[int, Query()],
    hx_target: HxTarget,
) -> HTMLResponse:
    with session:
        if (alerts := maybe_alerts_if_group_locked(request, session, adventuring_group_id)) is not None:
            print("ALERTS", alerts)
            return alerts
        current_group = session.get(AdventuringGroup, adventuring_group_id)
        time_slot_id = current_group.time_slot_id
        remove_person_from_group(session, current_group, user.id)
        session.commit()
    return await schedule(request, user, session, hx_target, time_slot_id)


def maybe_alerts_if_group_locked(
    request: Request, session: Session, group_id: int, retarget: str = ""
) -> Response | None:
    statement = select(CommittedAllocationResult).where(CommittedAllocationResult.adventuring_group_id == group_id)
    if session.exec(statement).first() is None:
        return None
    return alerts_template_response(
        [Alert("Your game is already assigned, you can't take this action - please refresh", "error")], request
    )


@router.get("/schedule")
async def schedule(
    request: Request,
    user: User,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Query()] = 1,
    additional_response_headers: dict[str, str] | None = None,
) -> HTMLResponse:
    if user is None:
        return templates.TemplateResponse(
            name="main/login.html.jinja",
            context={"request": request, "alerts": [Alert("Please log in to view your schedule", "warning")]},
            block_name=hx_target,
            headers={"HX-Redirect": "/me", "HX-Push-Url": "/me"},
        )

    with session:
        # Get the current adventuring group for this time slot
        adventuring_group = get_adventuring_group_from_user_and_time_slot_id(session, user.id, time_slot_id)
        adventuring_group = AdventuringGroupWithExtra.model_validate(adventuring_group)

        # Possibly GMing a game this time slot
        statement = (
            select(Game)
            .join(
                TableAllocation,
                (TableAllocation.game_id == Game.id) & (TableAllocation.time_slot_id == time_slot_id),
            )
            .where(Game.gamemaster_id == user.id)
        )
        gm_game = session.exec(statement).first()

        if gm_game:
            gm_game = GameWithExtra.model_validate(gm_game)

        # Get all of the games and existing preferences for this time slot
        statement = (
            select(Game, TableAllocation, SessionPreference)
            .join(
                TableAllocation,
                (TableAllocation.game_id == Game.id) & (TableAllocation.time_slot_id == time_slot_id),
            )
            .outerjoin(
                SessionPreference,
                (SessionPreference.adventuring_group_id == adventuring_group.id)
                & (SessionPreference.table_allocation_id == TableAllocation.id),
            )
            .group_by(Game.id)
            .filter(~Game.hidden)
            .order_by(Game.title)
        )
        preferences_data = session.exec(statement).all()
        preferences_data = [
            (
                GameWithExtra.model_validate(game),
                table_allocation,
                str(session_preference.preference if session_preference is not None else 3),
            )
            for game, table_allocation, session_preference in preferences_data
            if not gm_game or game.id != gm_game.id
        ]

        # And finally the actual time slot
        time_slot = session.get(TimeSlot, time_slot_id)

        statement = (
            select(TableAllocation)
            .join(CommittedAllocationResult, TableAllocation.id == CommittedAllocationResult.table_allocation_id)
            .where(
                (CommittedAllocationResult.adventuring_group_id == adventuring_group.id)
                & (TableAllocation.time_slot_id == time_slot_id)
            )
        )
        committed_table_allocation = session.exec(statement).first()
        if committed_table_allocation:
            committed_table_allocation = TableAllocationResultView.model_validate(committed_table_allocation)
            table_summary = extract_table_summary(
                committed_table_allocation, {committed_table_allocation.game.gamemaster_id}
            )
        else:
            table_summary = None

    push_url = f"/schedule?time_slot_id={time_slot_id}"

    return templates.TemplateResponse(
        name="main/schedule.html.jinja",
        context={
            "preferences_data": preferences_data,
            "gm_game": gm_game,
            "time_slot": time_slot,
            "adventuring_group": adventuring_group,
            "committed_table_allocation": committed_table_allocation,
            "table_summary": table_summary,
            "request": request,
            "user": user,
        },
        headers={"HX-Push-Url": push_url} | (additional_response_headers or {}),
        block_name=hx_target,
    )


# endregion

# region Partials


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
    hx_target: HxTarget,
) -> HTMLResponse:
    with session:
        user.name = name
        session.add(user)
        session.commit()
        session.refresh(user)
    return await me(request, user, hx_target)


# endregion

# region Utility


@router.post("/preferences")
async def preferences_post(
    request: Request,
    user: User,
    session: Session,
) -> HTMLResponse:
    form_data = await request.form()
    table_allocation_ratings = RatingForm.model_validate(form_data)
    rerender_time_slot_id = None

    with session:
        session_preferences: list[SessionPreference] = []
        adventuring_group: AdventuringGroup | None = None
        for table_allocation_id, rating in table_allocation_ratings.items():
            table_allocation = session.get(TableAllocation, table_allocation_id)

            if adventuring_group is None or adventuring_group.time_slot_id != table_allocation.time_slot_id:
                adventuring_group = get_adventuring_group_from_user_and_time_slot_id(
                    session, user.id, table_allocation.time_slot_id
                )
                adventuring_group_id = adventuring_group.id

                if table_allocation.time_slot.is_open_for_checkin and not adventuring_group.checked_in:
                    adventuring_group.checked_in = True
                    rerender_time_slot_id = adventuring_group.time_slot_id

                session.add(adventuring_group)

                if (alerts := maybe_alerts_if_group_locked(request, session, adventuring_group_id)) is not None:
                    return alerts

            session_preference = SessionPreference(
                preference=rating.numeric(),
                adventuring_group_id=adventuring_group_id,
                table_allocation_id=table_allocation_id,
            )

            session_preferences.append(session_preference)
        statement = sqlite_upsert(SessionPreference).values([pref.model_dump() for pref in session_preferences])
        statement = statement.on_conflict_do_update(
            set_={"preference": statement.excluded.preference},
        )
        session.exec(statement)
        session.commit()

    if rerender_time_slot_id is not None:
        return await schedule(
            request,
            user,
            session,
            hx_target="checkin_contents",
            time_slot_id=rerender_time_slot_id,
            additional_response_headers={
                "HX-Retarget": "#checkin_contents",
                "HX-Reswap": "innerHTML",
            },
        )
    else:
        return HTMLResponse(status_code=204)


@router.post("/checkin")
async def checkin_post(
    request: Request,
    user: User,
    session: Session,
    time_slot_id: Annotated[int, Query()],
    checkin: Annotated[bool, Form()] = False,
) -> HTMLResponse:
    with session:
        adventuring_group = get_adventuring_group_from_user_and_time_slot_id(session, user.id, time_slot_id)
        adventuring_group.checked_in = checkin
        session.add(adventuring_group)
        session.commit()
    return HTMLResponse(status_code=204)


# endregion


# region Admin


def maybe_alerts_from_auth(auth: tuple[bool, list[Exception]], request: Request) -> Response | None:
    if auth[0]:
        return None
    alerts = [Alert(str(e), "error") for e in auth[1]]
    return alerts_template_response(alerts, request)


@router.post("/admin/run_allocate")
async def run_allocate(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
    engine: EngineDependency,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts
    allocation_results = do_allocation(time_slot_id, engine, force_override=True)
    return await admin_allocate(request, session, hx_target, time_slot_id)


def do_commit_or_rollback(
    session: Session,
    time_slot_id: int,
    *,
    from_table: type[CommittedAllocationResult] | type[AllocationResult],
    to_table: type[CommittedAllocationResult] | type[AllocationResult],
):
    with session:
        # Delete all existing in to_table for this time slot
        statement = (
            select(to_table)
            .join(TableAllocation, TableAllocation.id == to_table.table_allocation_id)
            .where(TableAllocation.time_slot_id == time_slot_id)
        )
        existing_results = session.exec(statement).all()
        for existing_result in existing_results:
            session.delete(existing_result)

        # Copy all from from_table for this time slot to to_table
        statement = (
            select(from_table)
            .join(TableAllocation, TableAllocation.id == from_table.table_allocation_id)
            .where(TableAllocation.time_slot_id == time_slot_id)
        )
        allocation_results = session.exec(statement).all()

        for allocation_result in allocation_results:
            session.add(
                to_table(
                    table_allocation_id=allocation_result.table_allocation_id,
                    adventuring_group_id=allocation_result.adventuring_group_id,
                )
            )
        session.commit()


@router.post("/admin/commit_allocate")
async def commit_allocate(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts
    do_commit_or_rollback(session, time_slot_id, from_table=AllocationResult, to_table=CommittedAllocationResult)
    return await admin_allocate(request, session, hx_target, time_slot_id)


@router.post("/admin/rollback_allocate")
async def rollback_allocate(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts
    do_commit_or_rollback(session, time_slot_id, from_table=CommittedAllocationResult, to_table=AllocationResult)
    return await admin_allocate(request, session, hx_target, time_slot_id)


@router.post("/admin/uncommit_allocate")
async def uncommit_allocate(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts
    with session:
        # Delete all existing in CommittedAllocationResult for this time slot
        statement = (
            select(CommittedAllocationResult)
            .join(TableAllocation, TableAllocation.id == CommittedAllocationResult.table_allocation_id)
            .where(TableAllocation.time_slot_id == time_slot_id)
        )
        existing_results = session.exec(statement).all()
        for existing_result in existing_results:
            session.delete(existing_result)
        session.commit()
    return await admin_allocate(request, session, hx_target, time_slot_id)


def revert_applied_compensations_for_time_slot(session: Session, time_slot_id: int):
    # Delete all existing unapplied compensations for this time slot
    existing_compensations_this_time_slot = session.exec(
        select(Compensation).where(Compensation.time_slot_id == time_slot_id).where(~Compensation.applied)
    ).all()
    for compensation in existing_compensations_this_time_slot:
        session.delete(compensation)

    # Get and revert existing applied compensations
    existing_compensations_this_time_slot = session.exec(
        select(Compensation).where(Compensation.time_slot_id == time_slot_id).where(Compensation.applied)
    ).all()

    for compensation in existing_compensations_this_time_slot:
        compensation.person.compensation -= compensation.compensation_delta
        compensation.person.golden_d20s -= compensation.golden_d20_delta
        compensation.applied = False
        session.add(compensation)


@router.post("/admin/compensate_draft")
async def compensate_draft(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
    engine: EngineDependency,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts

    compensations = get_compensation(time_slot_id, engine, result_table="allocation_results")

    with session:
        revert_applied_compensations_for_time_slot(session, time_slot_id)

        for compensation in compensations:
            session.add(compensation)

        session.commit()

    return await admin_allocate(request, session, hx_target, time_slot_id)


@router.post("/admin/compensate_apply")
async def compensate_apply(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Form()],
    engine: EngineDependency,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts

    compensations = get_compensation(time_slot_id, engine)

    with session:
        revert_applied_compensations_for_time_slot(session, time_slot_id)

        # Apply new compensations
        for compensation in compensations:
            person = session.get(Person, compensation.person_id)
            person.compensation += compensation.compensation_delta
            person.golden_d20s += compensation.golden_d20_delta
            compensation.applied = True
            session.add(compensation)

        session.commit()

    return await admin_allocate(request, session, hx_target, time_slot_id)


@dataclass
class GroupSummary:
    id: int
    members: list[Person]
    is_gm: bool
    is_gm_any_game: bool
    is_committed: bool
    is_checked_in: bool


def extract_table_summary(table_allocation: TableAllocationResultView, gm_ids: set) -> dict[str, Any]:
    table_groups: list[GroupSummary] = []
    for allocation_result in table_allocation.allocation_results:
        adventuring_group = allocation_result.adventuring_group
        comitted_group_ids = {
            committed_allocation_result.adventuring_group_id
            for committed_allocation_result in table_allocation.committed_allocation_results
        }
        table_groups.append(
            GroupSummary(
                id=adventuring_group.id,
                members=adventuring_group.members,
                is_gm=adventuring_group.members[0].id == table_allocation.game.gamemaster_id,
                is_gm_any_game=adventuring_group.members[0].id in gm_ids,
                is_committed=adventuring_group.id in comitted_group_ids,
                is_checked_in=adventuring_group.checked_in,
            )
        )
        # Put the GM at the front of the list always
        gm_index = next((i for i, group in enumerate(table_groups) if group.is_gm), None)
        if gm_index is not None:
            table_groups.insert(0, table_groups.pop(gm_index))
    table_summary = {
        "has_gm": any(group.is_gm for group in table_groups),
        "total_players": sum(len(group.members) for group in table_groups if not group.is_gm),
        "groups": table_groups,
    }
    return table_summary


@router.get("/admin/allocate")
async def admin_allocate(
    request: Request,
    session: Session,
    hx_target: HxTarget,
    time_slot_id: Annotated[int, Query()] = 1,
) -> HTMLResponse:
    with session:
        # Get all of the allocation results for this time slot
        statement = (
            select(TableAllocation)
            .where(TableAllocation.time_slot_id == time_slot_id)
            .order_by(TableAllocation.table_id)
        )
        table_allocations = session.exec(statement).all()
        table_allocations = [
            TableAllocationResultView.model_validate(table_allocation) for table_allocation in table_allocations
        ]

        # Get the actual time slot
        time_slot = session.get(TimeSlot, time_slot_id)

    table_summaries: dict[int, dict[str, Any]] = {}

    gm_ids = {table_allocation.game.gamemaster_id for table_allocation in table_allocations}

    for table_allocation in table_allocations:
        table_summaries[table_allocation.id] = extract_table_summary(table_allocation, gm_ids)

    with session:
        # Get everyone not in a group
        statement = select(Person).where(
            ~exists(
                select(AdventuringGroup)
                .where(AdventuringGroup.time_slot_id == time_slot_id)
                .join(
                    PersonAdventuringGroupLink, PersonAdventuringGroupLink.adventuring_group_id == AdventuringGroup.id
                )
                .where(PersonAdventuringGroupLink.member_id == Person.id)
            )
        )
        ungrouped_people = session.exec(statement).all()
        # Create a default group for them
        if ungrouped_people:
            for person in ungrouped_people:
                create_initial_adventuring_group(session, person, time_slot_id, checked_in=False)
            session.commit()

        # Get every group not assigned anywhere
        statement = (
            select(AdventuringGroup)
            .where(AdventuringGroup.time_slot_id == time_slot_id)
            .outerjoin(AllocationResult, AllocationResult.adventuring_group_id == AdventuringGroup.id)
            .where(AllocationResult.id.is_(None))
        )
        unallocated_groups = session.exec(statement).all()
        unallocated_groups = sorted(
            [AdventuringGroupWithExtra.model_validate(group) for group in unallocated_groups],
            key=lambda group: group.members[0].name.lower(),
        )
        unallocated_groups = [
            GroupSummary(
                id=group.id,
                members=group.members,
                is_gm=False,
                is_gm_any_game=group.members[0].id in gm_ids,
                is_committed=False,
                is_checked_in=group.checked_in,
            )
            for group in unallocated_groups
        ]

    compensation_summaries: dict[int, dict[Literal["applied", "draft"], Compensation]] = {}

    with session:
        # Get the compensations for this time slot
        statement = select(Compensation).where(Compensation.time_slot_id == time_slot_id)
        compensations = session.exec(statement).all()
        for compensation in compensations:
            if compensation.person_id not in compensation_summaries:
                compensation_summaries[compensation.person_id] = {}
            if compensation.applied:
                compensation_summaries[compensation.person_id]["applied"] = compensation
            else:
                compensation_summaries[compensation.person_id]["draft"] = compensation

    return templates.TemplateResponse(
        name="main/allocate.html.jinja",
        context={
            "time_slot": time_slot,
            "table_allocations": table_allocations,
            "table_summaries": table_summaries,
            "unallocated_groups": unallocated_groups,
            "compensation_summaries": compensation_summaries,
            "request": request,
        },
        block_name=hx_target,
    )


@router.get("/admin/move_menu")
async def move_menu(
    request: Request,
    session: Session,
    group_id: Annotated[int, Query()],
    time_slot_id: Annotated[int, Query()],
) -> HTMLResponse:
    with session:
        statement = (
            select(
                TableAllocation.id.label("table_allocation_id"),
                Game.title.label("title"),
                SessionPreference.preference.label("preference"),
                Table.number.label("table_number"),
            )
            .where(TableAllocation.time_slot_id == time_slot_id)
            .join(Game, Game.id == TableAllocation.game_id)
            .join(Table, Table.id == TableAllocation.table_id)
            .outerjoin(
                SessionPreference,
                (SessionPreference.adventuring_group_id == group_id)
                & (SessionPreference.table_allocation_id == TableAllocation.id),
            )
            .order_by(TableAllocation.table_id)
        )
        query_results = session.exec(statement).all()
        candidates = [
            {description["name"]: value for description, value in zip(statement.column_descriptions, row)}
            for row in query_results
        ]
        candidates.append(
            {
                "table_allocation_id": -1,
                "title": "Unassigned",
                "preference": 0,
                "table_number": None,
            }
        )

        current_table_allocation_id = (
            session.exec(
                select(TableAllocation.id)
                .join(AllocationResult, AllocationResult.table_allocation_id == TableAllocation.id)
                .where(AllocationResult.adventuring_group_id == group_id)
            ).first()
            or -1
        )

    return templates.TemplateResponse(
        name="shared/partials/move_menu.html.jinja",
        context={
            "request": request,
            "group_id": group_id,
            "time_slot_id": time_slot_id,
            "current_table_allocation_id": current_table_allocation_id,
            "candidates": candidates,
        },
    )


@router.get("/admin/move_button")
async def move_button(
    request: Request,
    group_id: Annotated[int, Query()],
    time_slot_id: Annotated[int, Query()],
) -> HTMLResponse:
    return templates.TemplateResponse(
        name="shared/partials/move_button.html.jinja",
        context={
            "request": request,
            "group_id": group_id,
            "time_slot_id": time_slot_id,
        },
    )


@router.put("/admin/move")
async def move(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    group_id: Annotated[int, Query()],
    table_allocation_id: Annotated[int, Form()] = -1,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts

    with session:
        adventuring_group = session.get(AdventuringGroup, group_id)
        time_slot_id = adventuring_group.time_slot_id

        current_table_allocation_and_result = session.exec(
            select(TableAllocation, AllocationResult)
            .join(AllocationResult, TableAllocation.id == AllocationResult.table_allocation_id)
            .where(AllocationResult.adventuring_group_id == group_id)
        ).first()

        if table_allocation_id != -1:
            # Check the table exists
            new_table_allocation = session.get(TableAllocation, table_allocation_id)
            if new_table_allocation is None:
                return alerts_template_response([Alert("Table not found, woops", "error")], request)
            # Add the new allocation result
            new_table_allocation.allocation_results.append(AllocationResult(adventuring_group_id=group_id))

        if current_table_allocation_and_result is None and table_allocation_id == -1:
            return alerts_template_response([Alert("Already unassigned", "warning")], request)

        if current_table_allocation_and_result is not None:
            current_table_allocation, current_allocation_result = current_table_allocation_and_result
            if current_table_allocation.id == table_allocation_id:
                return alerts_template_response([Alert("Already at this table", "warning")], request)
            # Remove the old allocation result
            session.delete(current_allocation_result)
        session.commit()
    return await admin_allocate(request, session, hx_target, time_slot_id)


@router.put("/admin/checkin")
async def checkin(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    hx_target: HxTarget,
    group_id: Annotated[int, Query()],
    checkin: Annotated[bool, Query()] = False,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts
    with session:
        adventuring_group = session.get(AdventuringGroup, group_id)
        adventuring_group.checked_in = checkin
        time_slot_id = adventuring_group.time_slot_id
        session.add(adventuring_group)
        session.commit()
    return await admin_allocate(request, session, hx_target, time_slot_id)


@router.get("/admin/players")
async def admin_players(
    request: Request,
    session: Session,
    hx_target: HxTarget,
) -> HTMLResponse:
    with session:
        statement = select(Person).order_by(Person.name)
        people = session.exec(statement).all()
        people = [PersonWithExtra.model_validate(person) for person in people]
    return templates.TemplateResponse(
        name="main/players.html.jinja",
        context={
            "people": people,
            "request": request,
        },
        block_name=hx_target,
    )


@router.get("/admin/person_row_view")
async def admin_person_row_view(
    request: Request,
    session: Session,
    person_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    if person_id is None:
        return HTMLResponse(content="", status_code=200)

    with session:
        person = session.get(Person, person_id)
        person = PersonWithExtra.model_validate(person)
    return templates.TemplateResponse(
        name="shared/partials/person_row_view.html.jinja",
        context={
            "person": person,
            "request": request,
        },
    )


@router.get("/admin/person_row_edit")
async def admin_person_row_edit(
    request: Request,
    session: Session,
    person_id: Annotated[int | None, Query()] = None,
    create: Annotated[bool, Query()] = False,
) -> HTMLResponse:
    with session:
        if create:
            person = Person(name="", email="")
        else:
            person = session.get(Person, person_id)
    return templates.TemplateResponse(
        name="shared/partials/person_row_edit.html.jinja",
        context={
            "person": person,
            "request": request,
        },
    )


@router.put("/admin/person_row_edit")
async def admin_person_row_edit_put(
    auth: AuthWithHandler,
    request: Request,
    session: Session,
    name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    golden_d20s: Annotated[int, Form()],
    compensation: Annotated[int, Form()],
    person_id: Annotated[int | None, Query()] = None,
) -> HTMLResponse:
    if (alerts := maybe_alerts_from_auth(auth, request)) is not None:
        return alerts

    new_person = PersonUpdate(
        name=name,
        email=email,
        golden_d20s=golden_d20s,
        compensation=compensation,
    )
    with session:
        try:
            if person_id is None:
                new_person = Person.model_validate(new_person)
                session.add(new_person)
                session.commit()
                session.refresh(new_person)
                person_id = new_person.id
            else:
                person = session.get(Person, person_id)
                person.sqlmodel_update(new_person)
                session.add(person)
                session.commit()
        except Exception as e:
            session.rollback()
            print(e)
            return alerts_template_response([Alert(str(e), "error")], request)
    return await admin_person_row_view(request, session, person_id)


# endregion
