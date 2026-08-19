from litestar import Controller, get
from litestar.di import Provide
from litestar.exceptions import HTTPException

from convergence_games.lib.ocean import Sqid, sink
from convergence_games.lib.request_type import Request
from convergence_games.lib.response_type import HTMXBlockTemplate, Template
from convergence_games.services import ImageLoader

from ..services import GameService, UserGameContext, provide_game_service


class GameController(Controller):
    path = "/game"
    dependencies = {"game_service": Provide(provide_game_service)}

    @get(path="/{game_sqid:str}")
    async def get_game(
        self,
        request: Request,
        game_sqid: Sqid,
        game_service: GameService,
        image_loader: ImageLoader,
    ) -> Template:
        game_id: int = sink(game_sqid)
        game = await game_service.get_game_for_detail(game_id)

        if game is None:
            raise HTTPException(status_code=404, detail="Game not found")

        if request.user:
            user_game_context = await game_service.get_user_game_context(
                game_id=game_id, user_id=request.user.id, event_id=game.event_id
            )
        else:
            user_game_context = UserGameContext(None, None, False)

        game_image_urls = await game_service.get_game_image_urls(game, image_loader)
        scheduled_sessions = await game_service.get_scheduled_sessions(game_id)

        return HTMXBlockTemplate(
            template_name="pages/game.html.jinja",
            block_name=request.htmx.target,
            context={
                "game": game,
                "game_image_urls": game_image_urls,
                "preference": user_game_context.preference,
                "user_game_played": user_game_context.user_game_played,
                "scheduled_sessions": scheduled_sessions,
                "has_d20": user_game_context.has_d20,
                "user": request.user,
            },
        )
