from uuid import uuid4

from litestar.datastructures import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
    Image,
    System,
)
from convergence_games.services import ImageLoader

from .._forms import SubmitGameForm


class GameService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create_by_name[T: System | Genre | ContentWarning](self, model_type: type[T], name: str) -> T:
        existing = await self._session.execute(select(model_type).where(model_type.name == name))
        existing = existing.scalars().one_or_none()
        if existing is not None:
            return existing
        return model_type(name=name)

    async def build_new_links(
        self, *, data: SubmitGameForm, game: Game
    ) -> tuple[list[GameGenreLink], list[GameContentWarningLink], list[GameRequirementTimeSlotLink]]:
        genre_links = [
            (
                GameGenreLink(game=game, genre_id=genre)
                if isinstance(genre, int)
                else GameGenreLink(game=game, genre=await self.get_or_create_by_name(Genre, genre.value))
            )
            for genre in data.genre
        ]
        content_warning_links = [
            (
                GameContentWarningLink(game=game, content_warning_id=content_warning)
                if isinstance(content_warning, int)
                else GameContentWarningLink(
                    game=game,
                    content_warning=await self.get_or_create_by_name(ContentWarning, content_warning.value),
                )
            )
            for content_warning in data.content_warning
        ]
        time_slot_links = [
            GameRequirementTimeSlotLink(game_requirement=game.game_requirement, time_slot_id=time_slot_id)
            for time_slot_id in data.available_time_slot
        ]
        return genre_links, content_warning_links, time_slot_links

    async def create_image(self, upload_file: UploadFile, image_loader: ImageLoader) -> Image:
        lookup = uuid4()
        await image_loader.save_image(await upload_file.read(), lookup)
        return Image(lookup_key=lookup)

    async def build_image_links(
        self, *, data: SubmitGameForm, game: Game, image_loader: ImageLoader
    ) -> list[GameImageLink]:
        return [
            GameImageLink(
                game=game,
                image=await self.create_image(image, image_loader),
                sort_order=i,
            )
            for i, image in enumerate(data.image)
            if isinstance(image, UploadFile)
        ]

    async def create_game(
        self, *, data: SubmitGameForm, event: Event, gamemaster_id: int, image_loader: ImageLoader
    ) -> Game:
        system_kwarg = (
            {"system_id": data.system}
            if isinstance(data.system, int)
            else {"system": await self.get_or_create_by_name(System, data.system.value)}
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
            gamemaster_id=gamemaster_id,
            event_id=event.id,
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
        genre_links, content_warning_links, time_slot_links = await self.build_new_links(
            data=data,
            game=new_game,
        )
        image_links = await self.build_image_links(
            data=data,
            game=new_game,
            image_loader=image_loader,
        )

        self._session.add(new_game)
        self._session.add_all(genre_links)
        self._session.add_all(content_warning_links)
        self._session.add_all(time_slot_links)
        self._session.add_all(image_links)

        await self._session.flush()
        await self._session.refresh(new_game)

        return new_game


async def provide_game_service(transaction: AsyncSession) -> GameService:
    return GameService(transaction)
