from typing import Annotated, TypeAlias, cast

from litestar import Controller, get, post
from litestar.exceptions import NotFoundException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel, BeforeValidator
from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameNarrativism,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
)
from convergence_games.db.models import (
    ContentWarning,
    Event,
    Game,
    GameContentWarningLink,
    GameGenreLink,
    GameRequirement,
    GameRequirementTimeSlotLink,
    Genre,
    System,
)
from convergence_games.db.ocean import Sqid, sink

SqidSingle: TypeAlias = Annotated[
    int,
    BeforeValidator(lambda sqid: sink(cast(Sqid, sqid))),
]
SqidList: TypeAlias = Annotated[
    list[int],
    BeforeValidator(
        lambda sqids: [sink(cast(Sqid, sqids))] if isinstance(sqids, str) else [sink(sqid) for sqid in sqids]
    ),
]

IntFlagValidator = BeforeValidator(lambda value: sum(map(int, value)) if isinstance(value, list) else int(value))


class SubmitGameForm(BaseModel):
    # Stuff that's used for Game
    title: str
    system: SqidSingle
    tagline: str = ""
    genre: SqidList
    tone: GameTone
    content_warning: SqidList
    crunch: GameCrunch
    narrativism: GameNarrativism
    player_count_minimum: int
    player_count_optimum: int
    player_count_maximum: int
    classification: GameClassification
    ksp: Annotated[GameKSP, IntFlagValidator] = GameKSP.NONE

    # Stuff that's used for GameRequirement
    times_to_run: int = 1
    available_time_slot: SqidList
    scheduling_notes: str = ""
    table_size_requirement: Annotated[GameTableSizeRequirement, IntFlagValidator] = GameTableSizeRequirement.NONE
    table_size_notes: str = ""
    equipment_requirement: Annotated[GameEquipmentRequirement, IntFlagValidator] = GameEquipmentRequirement.NONE
    equipment_notes: str = ""
    activity_requirement: Annotated[GameActivityRequirement, IntFlagValidator] = GameActivityRequirement.NONE
    activity_notes: str = ""
    room_requirement: Annotated[GameRoomRequirement, IntFlagValidator] = GameRoomRequirement.NONE
    room_notes: str = ""


class GamesController(Controller):
    @get(path="/games")
    async def get_games(self, request: Request) -> Template:
        return HTMXBlockTemplate(template_name="pages/games.html.jinja", block_name=request.htmx.target)

    @get(path="/submit_game/{event_sqid:str}")
    async def get_submit_game(self, request: Request, db_session: AsyncSession, event_sqid: Sqid) -> Template:
        event_id = sink(event_sqid)
        event = (
            await db_session.execute(select(Event).options(selectinload(Event.time_slots)).where(Event.id == event_id))
        ).scalar_one_or_none()

        if not event:
            raise NotFoundException(detail="Event not found")

        print(event.time_slots)

        # TODO: Replace these with search queries
        all_systems = (await db_session.execute(select(System))).scalars().all()
        all_genres = (await db_session.execute(select(Genre))).scalars().all()
        all_content_warnings = (await db_session.execute(select(ContentWarning))).scalars().all()

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "systems": all_systems,
                "genres": all_genres,
                "content_warnings": all_content_warnings,
                "tones": GameTone,
                "crunches": GameCrunch,
                "narrativisms": GameNarrativism,
                "ksps": GameKSP,
                "table_size_requirements": GameTableSizeRequirement,
                "equipment_requirements": GameEquipmentRequirement,
                "activity_requirements": GameActivityRequirement,
                "room_requirements": GameRoomRequirement,
            },
        )

    @post(path="/submit_game/{event_sqid:str}")
    async def post_submit_game(
        self,
        request: Request,
        db_session: AsyncSession,
        event_sqid: Sqid,
        data: Annotated[SubmitGameForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> Template:
        # TODO: Use a guard instead of this check
        if not request.user:
            raise NotFoundException(detail="User not found")

        event_id = sink(event_sqid)
        event = (
            await db_session.execute(select(Event).options(selectinload(Event.time_slots)).where(Event.id == event_id))
        ).scalar_one_or_none()

        print(data)

        if not event:
            raise NotFoundException(detail="Event not found")

        new_game = Game(
            name=data.title,
            tagline=data.tagline,
            description="",  # TODO
            classification=data.classification,
            crunch=data.crunch,
            narrativism=data.narrativism,
            tone=data.tone,
            player_count_minimum=data.player_count_minimum,
            player_count_optimum=data.player_count_optimum,
            player_count_maximum=data.player_count_maximum,
            ksps=data.ksp,
            system_id=data.system,
            gamemaster=request.user,  # TODO: Get from session
            event_id=event_id,
            game_requirement=GameRequirement(
                times_to_run=data.times_to_run,  # TODO
                scheduling_notes=data.scheduling_notes,
                table_size_requirement=data.table_size_requirement,
                table_size_notes=data.table_size_notes,
                equipment_requirement=data.equipment_requirement,
                equipment_notes=data.equipment_notes,
                activity_requirement=data.activity_requirement,
                activity_notes=data.activity_notes,
                room_requirement=data.room_requirement,
                room_notes=data.room_notes,
            ),
        )

        # Genres, Content Warrnings, Available Time Slots
        new_genre_links = [GameGenreLink(game=new_game, genre_id=genre_id) for genre_id in data.genre]
        new_content_warning_links = [
            GameContentWarningLink(game=new_game, content_warning_id=content_warning_id)
            for content_warning_id in data.content_warning
        ]
        new_time_slot_links = [
            GameRequirementTimeSlotLink(game_requirement=new_game.game_requirement, time_slot_id=time_slot_id)
            for time_slot_id in data.available_time_slot
        ]
        new_links = new_genre_links + new_content_warning_links + new_time_slot_links

        print(new_game)
        print(new_links)

        async with db_session as session:
            session.add(new_game)
            session.add_all(new_links)

            await session.commit()

        return HTMXBlockTemplate(
            template_str="""
            <p>Submitted game for event {{ event_sqid }}</p>
            """,
            context={"event_sqid": event_sqid},
        )

    @get(path="/submit_game/system_search")
    async def get_system_search(self, request: Request, db_session: AsyncSession, search: str) -> Template:
        all_systems = (await db_session.execute(select(System).options(selectinload(System.aliases)))).scalars().all()

        # Match system name OR alias, pair with system object
        to_match: list[tuple[str, System]] = []
        for system in all_systems:
            to_match.append((system.name, system))
            for alias in system.aliases:
                to_match.append((alias.name, system))

        names_scores_indices = process.extract(
            query=search,
            choices=[name for name, _ in to_match],
            scorer=fuzz.WRatio,
            processor=utils.default_process,
            limit=10,
            score_cutoff=50,
        )
        print(names_scores_indices)
        # Deduplicate by system object, keep highest score
        top_systems: list[System] = []
        for _, score, index in names_scores_indices:
            system = to_match[index][1]
            if system not in top_systems:
                top_systems.append(system)
                print(f"Adding {system.name} to top systems: {score}")
        print(top_systems)
        return HTMXBlockTemplate(
            template_str="""
            <p>You searched for {{ search }}</p>
            <h1>Results:</h1>

            <table>
                <tr><th>System name</th><th>Match (possibly alias)</th><th>Score</th></tr>
                {% for name, score, index in systems_scores_indices %}
                    <tr><td>{{ to_match[index][1].name }}</td><td>"{{ name }}"</td><td>{{ score }}</td></tr>
                {% endfor %}
            </table>

            <h1>Final results in order:</h1>

            {% for system in top_systems %}
                <div>{{ system.name }}</div>
            {% endfor %}
            """,
            context={
                "search": search,
                "to_match": to_match,
                "systems_scores_indices": names_scores_indices,
                "top_systems": top_systems,
            },
        )
