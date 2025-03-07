from dataclasses import dataclass
from typing import Annotated, Callable, ClassVar, Generic, Protocol, TypeAlias, cast, runtime_checkable

from litestar import Controller, get, post
from litestar.exceptions import NotFoundException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel, BeforeValidator, ConfigDict, TypeAdapter
from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, selectinload

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
    Base,
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

# SqidSingle: TypeAlias = Annotated[
#     int,
#     BeforeValidator(lambda sqid: sink(cast(Sqid, sqid))),
# ]
# SqidList: TypeAlias = Annotated[
#     list[int],
#     BeforeValidator(
#         lambda sqids: [sink(cast(Sqid, sqids))] if isinstance(sqids, str) else [sink(sqid) for sqid in sqids]
#     ),
# ]


class NewValue[T](BaseModel):
    value: T


type SqidOrNew[T] = int | NewValue[T]


def make_sqid_or_new_validator[T](new_value_type: type[T]) -> Callable[[str], SqidOrNew[T]]:
    new_value_type_adapter = TypeAdapter(new_value_type)

    def sqid_or_new_validator(value: str) -> SqidOrNew[T]:
        if value.startswith("new:"):
            return NewValue(value=new_value_type_adapter.validate_python(value.removeprefix("new:")))
        return sink(cast(Sqid, value))

    return sqid_or_new_validator


MaybeListValidator = BeforeValidator(lambda value: [value] if isinstance(value, str) else value)
IntFlagValidator = BeforeValidator(lambda value: sum(map(int, value)) if isinstance(value, list) else int(value))
SqidOrNewStr = Annotated[SqidOrNew[str], BeforeValidator(make_sqid_or_new_validator(str))]


class SubmitGameForm(BaseModel):
    # Stuff that's used for Game
    title: str
    system: SqidOrNewStr
    tagline: str = ""
    genre: Annotated[list[SqidOrNewStr], MaybeListValidator]
    tone: GameTone
    content_warning: Annotated[list[SqidOrNewStr], MaybeListValidator]
    crunch: GameCrunch
    narrativism: GameNarrativism
    player_count_minimum: int
    player_count_optimum: int
    player_count_maximum: int
    classification: GameClassification
    ksp: Annotated[GameKSP, IntFlagValidator] = GameKSP.NONE

    # Stuff that's used for GameRequirement
    times_to_run: int = 1
    available_time_slot: Annotated[list[SqidOrNewStr], MaybeListValidator]
    scheduling_notes: str = ""
    table_size_requirement: Annotated[GameTableSizeRequirement, IntFlagValidator] = GameTableSizeRequirement.NONE
    table_size_notes: str = ""
    equipment_requirement: Annotated[GameEquipmentRequirement, IntFlagValidator] = GameEquipmentRequirement.NONE
    equipment_notes: str = ""
    activity_requirement: Annotated[GameActivityRequirement, IntFlagValidator] = GameActivityRequirement.NONE
    activity_notes: str = ""
    room_requirement: Annotated[GameRoomRequirement, IntFlagValidator] = GameRoomRequirement.NONE
    room_notes: str = ""


if __name__ == "__main__":
    game_form = SubmitGameForm.model_validate(
        {
            "title": "Test Game",
            "system": "new:Test System",
            "tagline": "A test game",
            "genre": ["new:Test Genre", "new:Test Genre 2", "Tdh1R"],
            "tone": "Goofy",
            "content_warning": "new:One Content Warning",
            "crunch": "Light",
            "narrativism": "Balanced",
            "player_count_minimum": 1,
            "player_count_optimum": 2,
            "player_count_maximum": 3,
            "classification": "PG",
            "ksp": 0,
            "times_to_run": 1,
            "available_time_slot": "W1r0j",
            # "scheduling_notes"
            # "table_size_requirement"
            # "table_size_notes"
            # "equipment_requirement"
            # "equipment_notes"
            # "activity_requirement"
            # "activity_notes"
            # "room_requirement"
            # "room_notes"
        }
    )
    print(game_form)
    exit()

type SearchableBase = System | Genre | ContentWarning


@dataclass
class SearchResult[T: SearchableBase]:
    name: str
    match: str
    score: float
    result: T


async def search_with_fuzzy_match[T: SearchableBase](
    db_session: AsyncSession, model_type: type[T], search: str
) -> list[SearchResult[T]]:
    # TODO: Can we directly query for the names (possibly including aliases) and sqids?
    query = select(model_type)

    if issubclass(model_type, System):
        query = query.options(selectinload(model_type.aliases))

    all_rows = (await db_session.execute(query)).scalars().all()

    to_match: list[tuple[str, T]] = []
    for row in all_rows:
        to_match.append((row.name, row))
        if isinstance(row, System):
            for alias in row.aliases:
                to_match.append((alias.name, row))

    names_scores_indices = process.extract(
        query=search,
        choices=[name for name, _ in to_match],
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        limit=10,
        score_cutoff=50,
    )

    already_matched_ids: set[int] = set()
    top_results: list[SearchResult[T]] = []

    for _, score, index in names_scores_indices:
        result = to_match[index][1]
        if result.id not in already_matched_ids:
            top_results.append(
                SearchResult(
                    name=result.name,
                    match=to_match[index][0],
                    score=score,
                    result=result,
                )
            )
            already_matched_ids.add(result.id)

    return top_results


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

    # Searches
    @get(path="/search/{name:str}")
    async def get_search(self, name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchContainer.html.jinja",
            context={"name": name},
        )

    @get(path="/search/system/results")
    async def get_system_search_results(self, db_session: AsyncSession, search: str) -> Template:
        results = await search_with_fuzzy_match(db_session, System, search)

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "system",
                "results": results,
                "search": search,
            },
        )

    @get(path="/search/system/select")
    async def get_system_search_selected(self, db_session: AsyncSession, sqid: Sqid) -> Template:
        system = await db_session.get(System, sink(sqid))

        if not system:
            raise NotFoundException(detail="System not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": system.name,
                "selected_sqid": sqid,
            },
        )

    @get(path="/search/system/new")
    async def get_system_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": selected_name,
                "new": True,
            },
        )
