from dataclasses import dataclass
from typing import Annotated, cast

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException, ValidationException
from litestar.params import Body, RequestEncodingType
from litestar.status_codes import HTTP_413_REQUEST_ENTITY_TOO_LARGE
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import (
    GameActivityRequirement,
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
    GameImageLink,
    GameRequirement,
    GameRequirementTimeSlotLink,
    Genre,
    System,
    User,
)
from convergence_games.lib.alerts import Alert, AlertError
from convergence_games.lib.deps import event_with, game_with
from convergence_games.lib.guards import permission_check, user_guard
from convergence_games.lib.permissions import user_has_permission
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template
from convergence_games.lib.template import catalog
from convergence_games.services import ImageLoader

from .._forms import SubmitGameForm
from ..services import GameService, provide_game_service


# region Permissions
def user_can_approve_game(user: User, game: Game) -> bool:
    return user_has_permission(user, "game", (game.event, game), "approve")


def user_can_edit_game(user: User, game: Game) -> bool:
    return user_has_permission(user, "game", (game.event, game), "update")


# endregion


class SubmissionStatusForm(BaseModel):
    submission_status: SubmissionStatus


# region Form Error
@dataclass
class FormError:
    field_name: str
    field_title: str
    errors: list[str]


def handle_submit_game_form_validation_error(request: Request, exc: ValidationException) -> HTMXBlockTemplate:
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


def handle_request_entity_too_large_error(request: Request, exc: HTTPException) -> HTMXBlockTemplate:
    raise AlertError(
        [
            Alert("alert-error", "Too much data for the server to handle! (Error 413)"),
            Alert("alert-error", "If you've submitted images, try reducing their total size below 20MB."),
        ]
    )


# endregion


# region Submit Game Controller
class SubmitGameController(Controller):
    dependencies = {"game_service": Provide(provide_game_service)}

    @get(
        path="/event/{event_sqid:str}/submit-game",
        guards=[user_guard],
        dependencies={"event": event_with(selectinload(Event.time_slots))},
    )
    async def get_submit_game(self, request: Request, event: Event, user: User) -> Template:
        if not event.is_submissions_open() and not user_has_permission(
            user, "event", (event, event), "manage_submissions"
        ):
            raise AlertError([Alert("alert-warning", "Game submissions are not currently open for this event.")])

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
                selectinload(Game.images),
            ),
            "permission": permission_check(user_can_edit_game),
        },
    )
    async def get_edit_game(
        self,
        request: Request,
        game: Game,
        permission: bool,
        image_loader: ImageLoader,
    ) -> Template:
        assert request.user is not None

        if not game.event.is_editing_open() and not user_has_permission(
            request.user, "event", (game.event, game.event), "manage_submissions"
        ):
            raise AlertError([Alert("alert-warning", "Game editing is not currently open for this event.")])

        for image in game.images:
            # TODO: This is a gross hack to get around the fact that we can't use the image loader in the template because of async
            image.baked_url = await image_loader.get_image_path(image.lookup_key)  # type: ignore

        return HTMXBlockTemplate(
            template_name="pages/submit_game.html.jinja",
            block_name=request.htmx.target,
            context={
                "event": game.event,
                "game": game,
                # TODO: Move these to globals
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
        path="/event/{event_sqid:str}/game",
        guards=[user_guard],
        dependencies={"event": event_with(selectinload(Event.time_slots))},
        exception_handlers={
            ValidationException: handle_submit_game_form_validation_error,
            HTTP_413_REQUEST_ENTITY_TOO_LARGE: handle_request_entity_too_large_error,
        },  # type: ignore[assignment]
        request_max_body_size=20 * 1024 * 1024,  # 20 MB
    )
    async def post_game(
        self,
        request: Request,
        event: Event,
        game_service: GameService,
        image_loader: ImageLoader,
        data: Annotated[SubmitGameForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        if not event.is_submissions_open() and not user_has_permission(
            request.user, "event", (event, event), "manage_submissions"
        ):
            raise AlertError([Alert("alert-warning", "Game submissions are not currently open for this event.")])

        new_game = await game_service.create_game(
            data=data, event=event, gamemaster_id=request.user.id, image_loader=image_loader
        )

        return HTMXBlockTemplate(
            re_target="#content",
            block_name="content",
            template_name="pages/submit_game_confirmation.html.jinja",
            context={"game": new_game},
        )

    @put(
        path="/game/{game_sqid:str}",
        guards=[user_guard],
        exception_handlers={
            ValidationException: handle_submit_game_form_validation_error,
            HTTP_413_REQUEST_ENTITY_TOO_LARGE: handle_request_entity_too_large_error,
        },  # type: ignore[assignment]
        request_max_body_size=20 * 1024 * 1024,  # 20 MB
        dependencies={
            "game": game_with(
                selectinload(Game.system),
                selectinload(Game.gamemaster),
                selectinload(Game.event).selectinload(Event.time_slots),
                selectinload(Game.game_requirement).selectinload(GameRequirement.time_slot_links),
                selectinload(Game.genre_links),
                selectinload(Game.content_warning_links),
                selectinload(Game.image_links),
            ),
            "permission": permission_check(user_can_edit_game),
        },
    )
    async def put_game(  # noqa: C901 - We know this is too complex, but it's tricky to change at the moment
        self,
        request: Request,
        transaction: AsyncSession,
        game_service: GameService,
        game: Game,
        permission: bool,
        image_loader: ImageLoader,
        data: Annotated[SubmitGameForm, Body(media_type=RequestEncodingType.MULTI_PART)],
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        if not game.event.is_editing_open() and not user_has_permission(
            request.user, "event", (game.event, game.event), "manage_submissions"
        ):
            raise AlertError([Alert("alert-warning", "Game editing is not currently open for this event.")])

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
            game.system = await game_service.get_or_create_by_name(System, data.system.value)
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
            genre if isinstance(genre, int) else await game_service.get_or_create_by_name(Genre, genre.value)
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
            else await game_service.get_or_create_by_name(ContentWarning, content_warning.value)
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

        # Images
        desired_image_ids_or_images = [
            image if isinstance(image, int) else await game_service.create_image(image, image_loader)
            for image in data.image
        ]
        # Remove any image links that are not in the desired list
        for image_link in game.image_links:
            if image_link.image_id not in desired_image_ids_or_images:
                await transaction.delete(image_link)
            else:
                # This image link is staying, so just update the sort order
                image_link.sort_order = desired_image_ids_or_images.index(image_link.image_id)
        # Add any new image links that are not already in the existing list
        for i, image_id_or_image in enumerate(desired_image_ids_or_images):
            if isinstance(image_id_or_image, int):
                # Technically since you won't share the same image ID across multiple games, this is a bit redundant
                # But maybe in future we will be sharing images across games/systems/etc
                if image_id_or_image in [link.image_id for link in game.image_links]:
                    # This image link already exists, so skip it
                    continue
                image_link = GameImageLink(game_id=game.id, image_id=image_id_or_image, sort_order=i)
            else:
                image_link = GameImageLink(game=game, image=image_id_or_image, sort_order=i)

            # Actually add it
            transaction.add(image_link)

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
