import itertools
from collections.abc import Sequence
from datetime import datetime, timezone

import humanize
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.models import Event, Game, Session

from .._common import PutEventManageScheduleSession


class ScheduleService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def unscheduled_games(self, event: Event) -> list[Game]:
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

        return unscheduled_games

    def sessions_by_table_and_time_slot(self, event: Event) -> dict[tuple[int, int], list[Session]]:
        return {
            (table.id, time_slot.id): [
                session
                for session in event.sessions
                if session.table_id == table.id
                and session.time_slot_id == time_slot.id
                and not session.committed  # Only show uncommitted (but saved) sessions
            ]
            for table in event.tables
            for time_slot in event.time_slots
        }

    def replace_sessions(
        self, event: Event, session_specs: Sequence[PutEventManageScheduleSession], *, commit: bool
    ) -> None:
        # Set the event's sessions to the new data - including deleting any existing sessions
        new_sessions: list[Session] = []

        if not commit:
            # We are not committing, so don't remove existing committed sessions
            new_sessions = [s for s in event.sessions if s.committed]

        for session_data in session_specs:
            new_sessions.append(
                Session(
                    game_id=session_data.game,
                    table_id=session_data.table,
                    time_slot_id=session_data.time_slot,
                    event_id=event.id,
                    committed=False,
                )
            )
            if commit:
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
        self._session.add(event)

    def last_updated_summary(self, event: Event, current_user_id: int, last_saved: datetime | None) -> str:
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
            if current_user_id != last_save_updater.id
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
            if current_user_id != last_commit_updater.id
            else "you"
        )
        last_commit_delta_string = (
            "" if last_commit_time is None else humanize.naturaltime(current_time - last_commit_time)
        )

        content = f"<span>Saved by {last_save_name_string} {last_save_delta_string}.</span><br><span>Committed by {last_commit_name_string} {last_commit_delta_string}.</span>"

        if last_saved is not None and last_save_time is not None and last_save_time > last_saved:
            content += "<br><span class='text-warning'>WARNING: This schedule has been updated since you last saved on this page, please review before saving or committing.</span>"

        return content


async def provide_schedule_service(transaction: AsyncSession) -> ScheduleService:
    return ScheduleService(transaction)
