from dataclasses import dataclass
from typing import Annotated, Callable, cast

from litestar import Controller, Response, get, post
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Body, RequestEncodingType
from pydantic import BaseModel, BeforeValidator, Field, TypeAdapter, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError
from rapidfuzz import fuzz, process, utils
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import ColumnExpressionArgument

from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.guards import user_guard
from convergence_games.app.request_type import Request
from convergence_games.app.response_type import HTMXBlockTemplate, Template
from convergence_games.db.enums import (
    GameActivityRequirement,
    GameClassification,
    GameCoreActivity,
    GameCrunch,
    GameEquipmentRequirement,
    GameKSP,
    GameRoomRequirement,
    GameTableSizeRequirement,
    GameTone,
    SubmissionStatus,
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
    title: Annotated[str, Field(min_length=1, max_length=100, title="Title")]
    system: Annotated[SqidOrNewStr, Field(title="System")]
    tagline: Annotated[str, Field(min_length=10, max_length=140, title="Tagline")] = ""
    description: Annotated[str, Field(title="Description")] = ""
    genre: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Genres")]
    tone: Annotated[GameTone, Field(title="Tone")]
    content_warning: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Content Warnings")] = []
    crunch: Annotated[GameCrunch, Field(title="Complexity")]
    core_activity: Annotated[GameCoreActivity, IntFlagValidator, Field(title="Core Activities")] = GameCoreActivity.NONE
    player_count_minimum: Annotated[int, Field(ge=1, title="Minimum Players")]
    player_count_minimum_more: int | None = None
    player_count_optimum: Annotated[int, Field(ge=1, title="Optimum Players")]
    player_count_optimum_more: int | None = None
    player_count_maximum: Annotated[int, Field(ge=1, title="Maximum Players")]
    player_count_maximum_more: int | None = None
    classification: Annotated[GameClassification, Field(title="Age Suitability & Classification")]
    ksp: Annotated[GameKSP, IntFlagValidator, Field(title="Bonuses")] = GameKSP.NONE

    # Stuff that's used for GameRequirement
    times_to_run: Annotated[int, Field(title="Times to Run")] = 1
    available_time_slot: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Available Time Slots")]
    scheduling_notes: Annotated[str, Field(title="Scheduling Notes")] = ""
    table_size_requirement: Annotated[
        GameTableSizeRequirement, IntFlagValidator, Field(title="Table Size Requirements")
    ] = GameTableSizeRequirement.NONE
    table_size_notes: Annotated[str, Field(title="Table Size Notes")] = ""
    equipment_requirement: Annotated[
        GameEquipmentRequirement, IntFlagValidator, Field(title="Equipment Requirements")
    ] = GameEquipmentRequirement.NONE
    equipment_notes: Annotated[str, Field(title="Equiment Notes")] = ""
    activity_requirement: Annotated[GameActivityRequirement, IntFlagValidator, Field(title="Activity Requirements")] = (
        GameActivityRequirement.NONE
    )
    activity_notes: Annotated[str, Field(title="Activity Notes")] = ""
    room_requirement: Annotated[GameRoomRequirement, IntFlagValidator, Field(title="Room Requirements")] = (
        GameRoomRequirement.NONE
    )
    room_notes: Annotated[str, Field(title="Room Notes")] = ""

    @field_validator("available_time_slot", mode="after")
    @classmethod
    def validate_enough_time_slots_selected(cls, value: list[SqidOrNewStr], info: ValidationInfo) -> list[SqidOrNewStr]:
        if len(value) < info.data["times_to_run"]:
            raise PydanticCustomError("", "You must select at least as many time slots as times to run.")
        return value


type SearchableBase = System | Genre | ContentWarning


@dataclass
class SearchResult[T: SearchableBase]:
    name: str
    match: str
    score: float
    result: T


async def search_with_fuzzy_match[T: SearchableBase](
    transaction: AsyncSession,
    model_type: type[T],
    search: str,
    extra_filters: ColumnExpressionArgument[bool] | None = None,
    suggested_on_empty: bool = False,
) -> list[SearchResult[T]]:
    # TODO: Can we directly query for the names (possibly including aliases) and sqids?
    query = select(model_type)

    if issubclass(model_type, System):
        query = query.options(selectinload(model_type.aliases))

    if extra_filters is not None:
        query = query.where(extra_filters)

    if not search:
        if suggested_on_empty:
            assert issubclass(model_type, Genre) or issubclass(model_type, ContentWarning)
            query = query.where(model_type.suggested).order_by(model_type.name)
            all_rows = (await transaction.execute(query)).scalars().all()
            return [
                SearchResult(
                    name=row.name,
                    match=row.name,
                    score=100,
                    result=row,
                )
                for row in all_rows
            ]
        else:
            return []

    all_rows = (await transaction.execute(query)).scalars().all()

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


@dataclass
class FormError:
    field_name: str
    field_title: str
    errors: list[str]


def handle_submit_game_form_validation_error(request: Request, exc: ValidationException) -> Response:
    print(request)
    print(exc)
    error_messages: dict[str, list[str]] = {}
    if exc.extra is not None:
        for extra in exc.extra:
            extra = cast(dict[str, str], extra)
            field_name = extra["key"]
            message = extra["message"]
            if field_name not in error_messages:
                error_messages[field_name] = []
            error_messages[field_name].append(message)

    form_errors: list[FormError] = [
        FormError(
            field_name=field_name, field_title=field_info.title or field_name, errors=error_messages.get(field_name, [])
        )
        for field_name, field_info in SubmitGameForm.model_fields.items()
    ]

    template_str = catalog.render("ErrorHolderOobCollection", form_errors=form_errors)
    return HTMXBlockTemplate(re_swap="none", template_str=template_str)


class SubmitGameController(Controller):
    @get(path="/submit-game", guards=[user_guard])
    async def get_submit_game(self, request: Request, transaction: AsyncSession) -> Template:
        # TODO 2026: Variable event ID to submit a game to
        event_id = 1
        event = (
            await transaction.execute(select(Event).options(selectinload(Event.time_slots)).where(Event.id == event_id))
        ).scalar_one_or_none()

        if not event:
            raise NotFoundException(detail="Event not found")

        # TODO: Replace these with search queries
        all_genres = (await transaction.execute(select(Genre).order_by(Genre.name))).scalars().all()
        all_content_warnings = (await transaction.execute(select(ContentWarning))).scalars().all()

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
                "genres": all_genres,
                "content_warnings": all_content_warnings,
                "tones": GameTone,
                "crunches": GameCrunch,
                "core_activities": GameCoreActivity,
                "ksps": GameKSP,
                "table_size_requirements": GameTableSizeRequirement,
                "equipment_requirements": GameEquipmentRequirement,
                "activity_requirements": GameActivityRequirement,
                "room_requirements": GameRoomRequirement,
            },
        )

    @post(
        path="/submit-game",
        guards=[user_guard],
        exception_handlers={ValidationException: handle_submit_game_form_validation_error},  # type: ignore[assignment]
    )
    async def post_submit_game(
        self,
        request: Request,
        transaction: AsyncSession,
        data: Annotated[SubmitGameForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> HTMXBlockTemplate:
        # TODO 2026: Variable event ID to submit a game to
        event_id = 1
        event = (
            await transaction.execute(select(Event).options(selectinload(Event.time_slots)).where(Event.id == event_id))
        ).scalar_one_or_none()

        print(data)

        if not event:
            raise NotFoundException(detail="Event not found")

        system_kwarg = (
            {"system_id": data.system} if isinstance(data.system, int) else {"system": System(name=data.system.value)}
        )

        new_game = Game(
            name=data.title,
            tagline=data.tagline,
            description=data.description,
            classification=data.classification,
            crunch=data.crunch,
            core_activity=data.core_activity,
            tone=data.tone,
            player_count_minimum=max(data.player_count_minimum, data.player_count_minimum_more or 0),
            player_count_optimum=max(data.player_count_optimum, data.player_count_optimum_more or 0),
            player_count_maximum=max(data.player_count_maximum, data.player_count_maximum_more or 0),
            ksps=data.ksp,
            **system_kwarg,
            gamemaster=request.user,
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

        async def create_if_not_exists[T: Genre | ContentWarning](
            model_type: type[T],
            name: str,
        ) -> T:
            existing = await transaction.execute(select(model_type).where(model_type.name == name))
            existing = existing.scalars().one_or_none()
            if existing is not None:
                return existing
            return model_type(name=name)

        # Genres, Content Warrnings, Available Time Slots
        new_genre_links = [
            (
                GameGenreLink(game=new_game, genre_id=genre)
                if isinstance(genre, int)
                else GameGenreLink(game=new_game, genre=await create_if_not_exists(Genre, genre.value))
            )
            for genre in data.genre
        ]
        new_content_warning_links = [
            (
                GameContentWarningLink(game=new_game, content_warning_id=content_warning)
                if isinstance(content_warning, int)
                else GameContentWarningLink(
                    game=new_game, content_warning=await create_if_not_exists(ContentWarning, content_warning.value)
                )
            )
            for content_warning in data.content_warning
        ]
        new_time_slot_links = [
            GameRequirementTimeSlotLink(game_requirement=new_game.game_requirement, time_slot_id=time_slot_id)
            for time_slot_id in data.available_time_slot
        ]
        new_links = new_genre_links + new_content_warning_links + new_time_slot_links

        transaction.add(new_game)
        transaction.add_all(new_links)

        await transaction.flush()
        await transaction.refresh(new_game)

        return HTMXBlockTemplate(
            re_target="#content",
            block_name="content",
            template_name="pages/submit_game_confirmation.html.jinja",
            context={"game": new_game},
        )

    # Searches
    @get(path="/search/{name:str}")
    async def get_search(self, name: str) -> Template:
        placeholders: dict[str, str] = {
            "system": "Search for a system...",
            "genre": "Search for genres...",
            "content_warning": "Search for content warnings...",
        }
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchContainer.html.jinja",
            context={"name": name, "placholder": placeholders.get(name, "Search...")},
        )

    @get(path="/search/system/results")
    async def get_system_search_results(self, request: Request, transaction: AsyncSession, search: str) -> Template:
        extra_filters = System.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (System.created_by == request.user.id)
        results = await search_with_fuzzy_match(transaction, System, search, extra_filters)

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "system",
                "results": results,
                "search": search,
                "mode": "select",
            },
        )

    @get(path="/search/system/select")
    async def get_system_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        system = await transaction.get(System, sink(sqid))

        if not system:
            raise NotFoundException(detail="System not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": system.name,
                "value": sqid,
            },
        )

    @get(path="/search/system/new")
    async def get_system_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchSelected.html.jinja",
            context={
                "name": "system",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )

    @get(path="/search/genre/results")
    async def get_genre_search_results(self, request: Request, transaction: AsyncSession, search: str) -> Template:
        extra_filters = Genre.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (Genre.created_by == request.user.id)
        results = await search_with_fuzzy_match(transaction, Genre, search, extra_filters, suggested_on_empty=True)

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "genre",
                "results": results,
                "search": search,
                "mode": "checks",
            },
        )

    @get(path="/search/genre/select")
    async def get_genre_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        genre = await transaction.get(Genre, sink(sqid))

        if not genre:
            raise NotFoundException(detail="Genre not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "genre",
                "selected_name": genre.name,
                "value": sqid,
            },
        )

    @get(path="/search/genre/new")
    async def get_genre_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "genre",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )

    @get(path="/search/content_warning/results")
    async def get_content_warning_search_results(
        self, request: Request, transaction: AsyncSession, search: str
    ) -> Template:
        extra_filters = ContentWarning.submission_status == SubmissionStatus.APPROVED
        if request.user:
            extra_filters = extra_filters | (ContentWarning.created_by == request.user.id)
        results = await search_with_fuzzy_match(
            transaction, ContentWarning, search, extra_filters, suggested_on_empty=True
        )

        return HTMXBlockTemplate(
            template_name="components/forms/search/SearchResultsList.html.jinja",
            context={
                "name": "content_warning",
                "results": results,
                "search": search,
                "mode": "checks",
            },
        )

    @get(path="/search/content_warning/select")
    async def get_content_warning_search_selected(self, transaction: AsyncSession, sqid: Sqid) -> Template:
        content_warning = await transaction.get(ContentWarning, sink(sqid))

        if not content_warning:
            raise NotFoundException(detail="Content warning not found")

        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "content_warning",
                "selected_name": content_warning.name,
                "value": sqid,
            },
        )

    @get(path="/search/content_warning/new")
    async def get_content_warning_search_new(self, selected_name: str) -> Template:
        return HTMXBlockTemplate(
            template_name="components/forms/search_checks/SearchCheckChip.html.jinja",
            context={
                "name": "content_warning",
                "selected_name": selected_name,
                "value": f"new:{selected_name}",
            },
        )
