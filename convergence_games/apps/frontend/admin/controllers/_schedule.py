import itertools
from datetime import datetime, timezone
from typing import Annotated

import humanize
from litestar import Controller, Response, get, put
from litestar.params import Body, Parameter, RequestEncodingType
from litestar.response import Template
from litestar.status_codes import HTTP_200_OK, HTTP_204_NO_CONTENT
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.db.models import Event, Game, GameRequirement, Room, Session, User
from convergence_games.lib.deps import event_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate

from .._common import SqidInt, user_can_manage_submissions


class PutEventManageScheduleSession(BaseModel):
    game: SqidInt
    table: SqidInt
    time_slot: SqidInt


class PutEventManageScheduleForm(BaseModel):
    sessions: list[PutEventManageScheduleSession]
    commit: bool = False


class ScheduleController(Controller):
    guards = [user_guard]
    dependencies = {"permission": permission_check(user_can_manage_submissions)}

    @get(
        path="/event/{event_sqid:str}/manage-schedule",
        dependencies={
            "event": event_with(
                selectinload(Event.games).options(
                    selectinload(Game.game_requirement).selectinload(GameRequirement.available_time_slots),
                    selectinload(Game.gamemaster),
                    selectinload(Game.sessions),
                ),
                selectinload(Event.rooms).selectinload(Room.tables),
                selectinload(Event.time_slots),
                selectinload(Event.tables),
                selectinload(Event.sessions).selectinload(Session.game),
            ),
        },
    )
    async def get_event_manage_schedule(
        self,
        request: Request,
        event: Event,
        permission: bool,
    ) -> Template:
        # Games duplicated by the number of times to run
        unscheduled_games = list(
            itertools.chain.from_iterable([game] * game.game_requirement.times_to_run for game in event.games)
        )

        # Remove games that have sessions already scheduled
        for session in event.sessions:
            # Only look for uncommitted sessions, since that's what we display to admins editing the current save
            if session.committed:
                continue
            # Remove one instance of the game from unscheduled games
            if session.game in unscheduled_games:
                unscheduled_games.remove(session.game)
            else:
                print("!!!! WARNING: Session game not found in unscheduled games - count mismatch", session.game.name)

        return HTMXBlockTemplate(
            template_name="pages/event_manage_schedule.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "unscheduled_games": unscheduled_games,
                "sessions_by_table_and_time_slot": {
                    (table.id, time_slot.id): [
                        session
                        for session in event.sessions
                        if session.table_id == table.id
                        and session.time_slot_id == time_slot.id
                        and not session.committed  # Only show uncommitted (but saved) sessions
                    ]
                    for table in event.tables
                    for time_slot in event.time_slots
                },
            },
        )

    @put(
        path="/event/{event_sqid:str}/manage-schedule",
        dependencies={
            "event": event_with(
                selectinload(Event.sessions),
            ),
        },
    )
    async def put_event_manage_schedule(
        self,
        event: Event,
        permission: bool,
        transaction: AsyncSession,
        data: Annotated[PutEventManageScheduleForm, Body(media_type=RequestEncodingType.JSON)],
    ) -> Response[str]:
        print(data)
        # Set the event's sessions to the new data - including deleting any existing sessions
        new_sessions: list[Session] = []

        if not data.commit:
            # We are not committing, so don't remove existing committed sessions
            new_sessions = [s for s in event.sessions if s.committed]

        for session_data in data.sessions:
            new_sessions.append(
                Session(
                    game_id=session_data.game,
                    table_id=session_data.table,
                    time_slot_id=session_data.time_slot,
                    event_id=event.id,
                    committed=False,
                )
            )
            if data.commit:
                # Also add a committed session for the game
                new_sessions.append(
                    Session(
                        game_id=session_data.game,
                        table_id=session_data.table,
                        time_slot_id=session_data.time_slot,
                        event_id=event.id,
                        committed=True,
                    )
                )

        event.sessions = new_sessions

        # Save the event
        transaction.add(event)

        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @get(
        path="/event/{event_sqid:str}/manage-schedule/last-updated-by",
        dependencies={
            "event": event_with(
                selectinload(Event.sessions).selectinload(Session.updated_by_user),
            ),
        },
    )
    async def get_event_manage_schedule_last_updated(
        self,
        event: Event,
        user: User,
        last_saved: Annotated[datetime | None, Parameter(query="last-saved")] = None,
    ) -> Response[str]:
        current_time = datetime.now(tz=timezone.utc)

        last_saved_session = max(
            [s for s in event.sessions if not s.committed], key=lambda s: s.updated_at, default=None
        )
        last_save_updater = last_saved_session.updated_by_user if last_saved_session else None
        last_save_time = last_saved_session.updated_at if last_saved_session else None
        last_save_name_string = (
            "never"
            if last_save_updater is None
            else last_save_updater.full_name
            if user.id != last_save_updater.id
            else "you"
        )
        last_save_delta_string = "" if last_save_time is None else humanize.naturaltime(current_time - last_save_time)

        last_commit_session = max([s for s in event.sessions if s.committed], key=lambda s: s.updated_at, default=None)
        last_commit_updater = last_commit_session.updated_by_user if last_commit_session else None
        last_commit_time = last_commit_session.updated_at if last_commit_session else None
        last_commit_name_string = (
            "never"
            if last_commit_updater is None
            else last_commit_updater.full_name
            if user.id != last_commit_updater.id
            else "you"
        )
        last_commit_delta_string = (
            "" if last_commit_time is None else humanize.naturaltime(current_time - last_commit_time)
        )

        content = f"<span>Saved by {last_save_name_string} {last_save_delta_string}.</span><br><span>Committed by {last_commit_name_string} {last_commit_delta_string}.</span>"

        if last_saved is not None and last_save_time is not None and last_save_time > last_saved:
            content += "<br><span class='text-warning'>WARNING: This schedule has been updated since you last saved on this page, please review before saving or committing.</span>"

        return Response(
            content=content,
            status_code=HTTP_200_OK,
        )
