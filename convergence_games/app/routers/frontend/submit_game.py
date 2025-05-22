from dataclasses import dataclass
from typing import Annotated, Callable, Literal, cast

from litestar import Controller, Response, get, post, put
from litestar.datastructures import UploadFile
from litestar.di import Provide
from litestar.exceptions import NotFoundException, ValidationException
from litestar.params import Body, RequestEncodingType
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.base import ExecutableOption

from convergence_games.app.app_config.template_config import catalog
from convergence_games.app.guards import permission_check, user_guard
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
    User,
)
from convergence_games.db.ocean import Sqid, sink
from convergence_games.permissions import user_has_permission


# region Submit Game Form
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


NoneToEmpty = BeforeValidator(lambda value: "" if value is None else value)
MaybeListValidator = BeforeValidator(lambda value: value if isinstance(value, list) else [value])
IntFlagValidator = BeforeValidator(lambda value: sum(map(int, value)) if isinstance(value, list) else int(value))
SqidOrNewStr = Annotated[SqidOrNew[str], BeforeValidator(make_sqid_or_new_validator(str))]
SqidInt = Annotated[int, BeforeValidator(sink)]


def user_can_approve_game(user: User, game: Game) -> bool:
    return user_has_permission(user, "game", (game.event, game), "approve")


def user_can_edit_game(user: User, game: Game) -> bool:
    return user_has_permission(user, "game", (game.event, game), "update")


class SubmitGameForm(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)  # Required for UploadFile

    # Stuff that's used for Game
    title: Annotated[str, Field(min_length=1, max_length=100, title="Title")]
    system: Annotated[SqidOrNewStr, Field(title="System")]
    tagline: Annotated[str, Field(min_length=10, max_length=140, title="Tagline"), NoneToEmpty] = ""
    description: Annotated[str, Field(title="Description"), NoneToEmpty] = ""

    image: Annotated[list[UploadFile], MaybeListValidator] = []  # TODO: Or typeof existing image in the database

    genre: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Genres")]
    tone: Annotated[GameTone, Field(title="Tone")]
    content_warning: Annotated[list[SqidOrNewStr], MaybeListValidator, Field(title="Content Warnings")] = []
    crunch: Annotated[GameCrunch, Field(title="Complexity")]
    core_activity: Annotated[GameCoreActivity, IntFlagValidator, Field(title="Core Activities")] = GameCoreActivity.NONE
    player_count_minimum_more: int | None = None
    player_count_minimum: Annotated[int, Field(ge=1, title="Minimum Players")]
    player_count_optimum_more: int | None = None
    player_count_optimum: Annotated[int, Field(ge=1, title="Optimum Players")]
    player_count_maximum_more: int | None = None
    player_count_maximum: Annotated[int, Field(ge=1, title="Maximum Players")]
    classification: Annotated[GameClassification, Field(title="Age Suitability & Classification")]
    ksp: Annotated[GameKSP, IntFlagValidator, Field(title="Bonuses")] = GameKSP.NONE

    # Stuff that's used for GameRequirement
    times_to_run: Annotated[int, Field(title="Times to Run")] = 1
    available_time_slot: Annotated[list[SqidInt], MaybeListValidator, Field(title="Available Time Slots")]
    scheduling_notes: Annotated[str, Field(title="Scheduling Notes"), NoneToEmpty] = ""
    table_size_requirement: Annotated[
        GameTableSizeRequirement, IntFlagValidator, Field(title="Table Size Requirements")
    ] = GameTableSizeRequirement.NONE
    table_size_notes: Annotated[str, Field(title="Table Size Notes"), NoneToEmpty] = ""
    equipment_requirement: Annotated[
        GameEquipmentRequirement, IntFlagValidator, Field(title="Equipment Requirements")
    ] = GameEquipmentRequirement.NONE
    equipment_notes: Annotated[str, Field(title="Equiment Notes"), NoneToEmpty] = ""
    activity_requirement: Annotated[GameActivityRequirement, IntFlagValidator, Field(title="Activity Requirements")] = (
        GameActivityRequirement.NONE
    )
    activity_notes: Annotated[str, Field(title="Activity Notes"), NoneToEmpty] = ""
    room_requirement: Annotated[GameRoomRequirement, IntFlagValidator, Field(title="Room Requirements")] = (
        GameRoomRequirement.NONE
    )
    room_notes: Annotated[str, Field(title="Room Notes"), NoneToEmpty] = ""

    agree_to_code_of_conduct: Annotated[
        Literal["on"] | None, Field(title="Agree to Code of Conduct", validate_default=True)
    ] = None
    agree_to_use_safety_tools: Annotated[
        Literal["on"] | None, Field(title="Agree to Use Safety Tools", validate_default=True)
    ] = None

    @property
    def player_count_minimum_prop(self) -> int:
        return max(self.player_count_minimum, self.player_count_minimum_more or 0)

    @property
    def player_count_optimum_prop(self) -> int:
        return max(self.player_count_optimum, self.player_count_optimum_more or 0)

    @property
    def player_count_maximum_prop(self) -> int:
        return max(self.player_count_maximum, self.player_count_maximum_more or 0)

    @field_validator("player_count_optimum", mode="after")
    @classmethod
    def validate_player_count_optimum(cls, value: int, info: ValidationInfo) -> int:
        minimum = max(info.data["player_count_minimum"], info.data["player_count_minimum_more"] or 0)
        optimum = max(value, info.data["player_count_optimum_more"] or 0)
        if optimum < minimum:
            raise PydanticCustomError("", "Optimum player count must be greater than or equal to minimum player count.")
        return value

    @field_validator("player_count_maximum", mode="after")
    @classmethod
    def validate_player_count_maximum(cls, value: int, info: ValidationInfo) -> int:
        optimum = max(info.data["player_count_optimum"], info.data["player_count_optimum_more"] or 0)
        maximum = max(value, info.data["player_count_maximum_more"] or 0)
        if maximum < optimum:
            raise PydanticCustomError("", "Maximum player count must be greater than or equal to optimum player count.")
        return value

    @field_validator("available_time_slot", mode="after")
    @classmethod
    def validate_enough_time_slots_selected(cls, value: list[SqidInt], info: ValidationInfo) -> list[SqidInt]:
        if len(value) < info.data["times_to_run"]:
            raise PydanticCustomError("", "You must select at least as many time slots as times to run.")
        return value

    @field_validator("agree_to_code_of_conduct", mode="after")
    @classmethod
    def validate_agree_to_code_of_conduct(cls, value: bool) -> bool:
        if not value:
            raise PydanticCustomError("", "You must agree to the Code of Conduct.")
        return value

    @field_validator("agree_to_use_safety_tools", mode="after")
    @classmethod
    def validate_agree_to_use_safety_tools(cls, value: bool) -> bool:
        if not value:
            raise PydanticCustomError("", "You must agree to use the X-Card and Open Table Policy.")
        return value


class SubmissionStatusForm(BaseModel):
    submission_status: SubmissionStatus


# endregion


# region Form Error
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


# endregion


# region Utility Functions
async def create_if_not_exists[T: System | Genre | ContentWarning](
    model_type: type[T],
    name: str,
    transaction: AsyncSession,
) -> T:
    existing = await transaction.execute(select(model_type).where(model_type.name == name))
    existing = existing.scalars().one_or_none()
    if existing is not None:
        return existing
    return model_type(name=name)


async def create_new_links(
    data: SubmitGameForm,
    transaction: AsyncSession,
    game: Game,
) -> tuple[list[GameGenreLink], list[GameContentWarningLink], list[GameRequirementTimeSlotLink]]:
    genre_links = [
        (
            GameGenreLink(game=game, genre_id=genre)
            if isinstance(genre, int)
            else GameGenreLink(game=game, genre=await create_if_not_exists(Genre, genre.value, transaction))
        )
        for genre in data.genre
    ]
    content_warning_links = [
        (
            GameContentWarningLink(game=game, content_warning_id=content_warning)
            if isinstance(content_warning, int)
            else GameContentWarningLink(
                game=game,
                content_warning=await create_if_not_exists(ContentWarning, content_warning.value, transaction),
            )
        )
        for content_warning in data.content_warning
    ]
    time_slot_links = [
        GameRequirementTimeSlotLink(game_requirement=game.game_requirement, time_slot_id=time_slot_id)
        for time_slot_id in data.available_time_slot
    ]
    return genre_links, content_warning_links, time_slot_links


def game_with(*options: ExecutableOption):
    async def wrapper(
        transaction: AsyncSession,
        game_sqid: Sqid,
    ) -> Game:
        game_id = sink(game_sqid)
        game = (
            await transaction.execute(select(Game).options(*options).where(Game.id == game_id))
        ).scalar_one_or_none()

        if not game:
            raise NotFoundException(detail="Game not found")

        return game

    return Provide(wrapper)


# endregion


# region Submit Game Controller
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

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": event,
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

    @get(
        path="/game/{game_sqid:str}/edit",
        guards=[user_guard],
        dependencies={
            "game": game_with(
                selectinload(Game.system),
                selectinload(Game.gamemaster),
                selectinload(Game.event).selectinload(Event.time_slots),
                selectinload(Game.game_requirement).selectinload(GameRequirement.available_time_slots),
                selectinload(Game.genres),
                selectinload(Game.content_warnings),
            ),
            "permission": permission_check(user_can_edit_game),
        },
    )
    async def get_edit_game(
        self,
        request: Request,
        game: Game,
        permission: bool,
    ) -> Template:
        assert request.user is not None

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": game.event,
                "game": game,
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
        path="/game",
        guards=[user_guard],
        exception_handlers={ValidationException: handle_submit_game_form_validation_error},  # type: ignore[assignment]
    )
    async def post_game(
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
            {"system_id": data.system}
            if isinstance(data.system, int)
            else {"system": await create_if_not_exists(System, data.system.value, transaction)}
        )

        new_game = Game(
            name=data.title,
            tagline=data.tagline,
            description=data.description,
            classification=data.classification,
            crunch=data.crunch,
            core_activity=data.core_activity,
            tone=data.tone,
            player_count_minimum=data.player_count_minimum_prop,
            player_count_optimum=data.player_count_optimum_prop,
            player_count_maximum=data.player_count_maximum_prop,
            ksps=data.ksp,
            **system_kwarg,
            gamemaster=request.user,
            event_id=event_id,
            game_requirement=GameRequirement(
                times_to_run=data.times_to_run,
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
        genre_links, content_warning_links, time_slot_links = await create_new_links(
            data=data,
            transaction=transaction,
            game=new_game,
        )
        new_links = genre_links + content_warning_links + time_slot_links

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

    @put(
        path="/game/{game_sqid:str}",
        guards=[user_guard],
        exception_handlers={ValidationException: handle_submit_game_form_validation_error},  # type: ignore[assignment]
        dependencies={
            "game": game_with(
                selectinload(Game.system),
                selectinload(Game.gamemaster),
                selectinload(Game.event).selectinload(Event.time_slots),
                selectinload(Game.game_requirement).selectinload(GameRequirement.time_slot_links),
                selectinload(Game.genre_links),
                selectinload(Game.content_warning_links),
            ),
            "permission": permission_check(user_can_edit_game),
        },
    )
    async def put_game(
        self,
        request: Request,
        transaction: AsyncSession,
        game: Game,
        permission: bool,
        data: Annotated[SubmitGameForm, Body(media_type=RequestEncodingType.MULTI_PART)],
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        # Update all the properties
        # This is kept in the same order as the POST method to make it easier to compare
        game.name = data.title
        game.tagline = data.tagline
        game.description = data.description
        game.classification = data.classification
        game.crunch = data.crunch
        game.core_activity = data.core_activity
        game.tone = data.tone
        game.player_count_minimum = data.player_count_minimum_prop
        game.player_count_optimum = data.player_count_optimum_prop
        game.player_count_maximum = data.player_count_maximum_prop
        game.ksps = data.ksp
        if isinstance(data.system, int):
            game.system_id = data.system
        else:
            game.system = await create_if_not_exists(System, data.system.value, transaction)
        # existing_game.gamemaster=request.user  - Not updated!
        # existing_game.event_id=event_id  - Not updated!

        game.game_requirement.times_to_run = data.times_to_run
        game.game_requirement.scheduling_notes = data.scheduling_notes
        game.game_requirement.table_size_requirement = data.table_size_requirement
        game.game_requirement.table_size_notes = data.table_size_notes
        game.game_requirement.equipment_requirement = data.equipment_requirement
        game.game_requirement.equipment_notes = data.equipment_notes
        game.game_requirement.activity_requirement = data.activity_requirement
        game.game_requirement.activity_notes = data.activity_notes
        game.game_requirement.room_requirement = data.room_requirement
        game.game_requirement.room_notes = data.room_notes

        # Reassign the links
        # TODO - This is a bit of a hack because we can't just automatically update the game requirement
        # For two reasons:
        # 1. This could be creating new Genres OR using existing ones
        # 2. It's not a true linking table because it's got extra data in it, so some ORM helpers don't work
        desired_genre_ids_or_new_genres = [
            genre if isinstance(genre, int) else await create_if_not_exists(Genre, genre.value, transaction)
            for genre in data.genre
        ]
        # Remove any genre links that are not in the desired list
        for genre_link in game.genre_links:
            if genre_link.genre_id not in desired_genre_ids_or_new_genres:
                await transaction.delete(genre_link)
        # Add any new genre links that are not already in the existing list
        for genre_id_or_new_genre in desired_genre_ids_or_new_genres:
            if isinstance(genre_id_or_new_genre, int):
                if genre_id_or_new_genre in [link.genre_id for link in game.genre_links]:
                    # This genre link already exists, so skip it
                    continue
                genre_link = GameGenreLink(game_id=game.id, genre_id=genre_id_or_new_genre)
            else:
                genre_link = GameGenreLink(game_id=game.id, genre=genre_id_or_new_genre)

            # Actually add it
            transaction.add(genre_link)

        # Do the same logic for content warnings
        desired_content_warning_ids_or_content_warnings = [
            content_warning
            if isinstance(content_warning, int)
            else await create_if_not_exists(ContentWarning, content_warning.value, transaction)
            for content_warning in data.content_warning
        ]
        # Remove any content warning links that are not in the desired list
        for content_warning_link in game.content_warning_links:
            if content_warning_link.content_warning_id not in desired_content_warning_ids_or_content_warnings:
                await transaction.delete(content_warning_link)
        # Add any new content warning links that are not already in the existing list
        for content_warning_id_or_new_content_warning in desired_content_warning_ids_or_content_warnings:
            if isinstance(content_warning_id_or_new_content_warning, int):
                if content_warning_id_or_new_content_warning in [
                    link.content_warning_id for link in game.content_warning_links
                ]:
                    # This content warning link already exists, so skip it
                    continue
                content_warning_link = GameContentWarningLink(
                    game_id=game.id, content_warning_id=content_warning_id_or_new_content_warning
                )
            else:
                content_warning_link = GameContentWarningLink(
                    game_id=game.id, content_warning=content_warning_id_or_new_content_warning
                )

            # Actually add it
            transaction.add(content_warning_link)

        # Time slots
        desired_time_slot_ids = data.available_time_slot
        # Remove any time slot links that are not in the desired list
        for time_slot_link in game.game_requirement.time_slot_links:
            if time_slot_link.time_slot_id not in desired_time_slot_ids:
                await transaction.delete(time_slot_link)
        # Add any new time slot links that are not already in the existing list
        for time_slot_id in desired_time_slot_ids:
            if time_slot_id in [link.time_slot_id for link in game.game_requirement.time_slot_links]:
                # This time slot link already exists, so skip it
                continue
            time_slot_link = GameRequirementTimeSlotLink(
                game_requirement=game.game_requirement, time_slot_id=time_slot_id
            )
            transaction.add(time_slot_link)

        transaction.add(game)

        return HTMXBlockTemplate(
            re_target="#content",
            block_name="content",
            template_name="pages/submit_game_confirmation.html.jinja",
            context={"game": game, "edited": True},
        )

    @put(
        path="/game/{game_sqid:str}/submission-status",
        guards=[user_guard],
        dependencies={
            "game": game_with(
                selectinload(Game.game_requirement),
                selectinload(Game.gamemaster),
                selectinload(Game.event),
                selectinload(Game.system),
            ),
            "permission": permission_check(user_can_approve_game),
        },
    )
    async def put_game_submission_status(
        self,
        request: Request,
        transaction: AsyncSession,
        game: Game,
        data: Annotated[SubmissionStatusForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        game.submission_status = data.submission_status
        transaction.add(game)

        template_str = catalog.render(
            "GameSubmissionRow",
            game=game,
            submission_status=SubmissionStatus,
            user=request.user,
        )
        return HTMXBlockTemplate(template_str=template_str)


# endregion
