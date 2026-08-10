from dataclasses import dataclass
from typing import Annotated, cast

from litestar import Controller, get, post, put
from litestar.di import Provide
from litestar.exceptions import HTTPException, ValidationException
from litestar.params import Body, RequestEncodingType
from litestar.status_codes import HTTP_413_REQUEST_ENTITY_TOO_LARGE
from pydantic import BaseModel
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
    Event,
    Game,
    GameRequirement,
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
    async def put_game(
        self,
        request: Request,
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

        game = await game_service.update_game(game=game, data=data, image_loader=image_loader)

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
        game_service: GameService,
        game: Game,
        data: Annotated[SubmissionStatusForm, Body(media_type=RequestEncodingType.URL_ENCODED)],
    ) -> HTMXBlockTemplate:
        assert request.user is not None

        game = await game_service.set_submission_status(game, data.submission_status)

        template_str = catalog.render(
            "GameSubmissionRow",
            game=game,
            submission_status=SubmissionStatus,
            user=request.user,
        )
        return HTMXBlockTemplate(template_str=template_str)


# endregion
