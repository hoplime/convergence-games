from dataclasses import dataclass
from uuid import uuid4

from litestar.datastructures import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from convergence_games.db.enums import SubmissionStatus, UserGamePreferenceValue
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
    Session,
    System,
    Table,
    UserEventD20Transaction,
    UserGamePlayed,
    UserGamePreference,
)
from convergence_games.services import ImageLoader

from .._forms import SubmitGameForm


@dataclass(slots=True)
class UserGameContext:
    preference: UserGamePreferenceValue | None
    user_game_played: UserGamePlayed | None
    has_d20: bool


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

    async def update_game(self, *, game: Game, data: SubmitGameForm, image_loader: ImageLoader) -> Game:
        """Precondition: game loaded with genre_links, content_warning_links, image_links,
        and game_requirement.time_slot_links (the game_with dep at _submit.py 524-533)."""
        self._apply_scalar_fields(game, data)
        await self._apply_system(game, data)
        await self._sync_genre_links(game, data)
        await self._sync_content_warning_links(game, data)
        await self._sync_time_slot_links(game, data)
        await self._sync_image_links(game, data, image_loader)
        self._session.add(game)
        return game

    def _apply_scalar_fields(self, game: Game, data: SubmitGameForm) -> None:
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

    async def _apply_system(self, game: Game, data: SubmitGameForm) -> None:
        if isinstance(data.system, int):
            game.system_id = data.system
        else:
            game.system = await self.get_or_create_by_name(System, data.system.value)
        # existing_game.gamemaster=request.user  - Not updated!
        # existing_game.event_id=event_id  - Not updated!

    async def _sync_genre_links(self, game: Game, data: SubmitGameForm) -> None:
        # Reassign the links
        # TODO - This is a bit of a hack because we can't just automatically update the game requirement
        # For two reasons:
        # 1. This could be creating new Genres OR using existing ones
        # 2. It's not a true linking table because it's got extra data in it, so some ORM helpers don't work
        desired_genre_ids_or_new_genres = [
            genre if isinstance(genre, int) else await self.get_or_create_by_name(Genre, genre.value)
            for genre in data.genre
        ]
        # Remove any genre links that are not in the desired list
        for genre_link in game.genre_links:
            if genre_link.genre_id not in desired_genre_ids_or_new_genres:
                await self._session.delete(genre_link)
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
            self._session.add(genre_link)

    async def _sync_content_warning_links(self, game: Game, data: SubmitGameForm) -> None:
        # Do the same logic for content warnings
        desired_content_warning_ids_or_content_warnings = [
            content_warning
            if isinstance(content_warning, int)
            else await self.get_or_create_by_name(ContentWarning, content_warning.value)
            for content_warning in data.content_warning
        ]
        # Remove any content warning links that are not in the desired list
        for content_warning_link in game.content_warning_links:
            if content_warning_link.content_warning_id not in desired_content_warning_ids_or_content_warnings:
                await self._session.delete(content_warning_link)
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
            self._session.add(content_warning_link)

    async def _sync_time_slot_links(self, game: Game, data: SubmitGameForm) -> None:
        # Time slots
        desired_time_slot_ids = data.available_time_slot
        # Remove any time slot links that are not in the desired list
        for time_slot_link in game.game_requirement.time_slot_links:
            if time_slot_link.time_slot_id not in desired_time_slot_ids:
                await self._session.delete(time_slot_link)
        # Add any new time slot links that are not already in the existing list
        for time_slot_id in desired_time_slot_ids:
            if time_slot_id in [link.time_slot_id for link in game.game_requirement.time_slot_links]:
                # This time slot link already exists, so skip it
                continue
            time_slot_link = GameRequirementTimeSlotLink(
                game_requirement=game.game_requirement, time_slot_id=time_slot_id
            )
            self._session.add(time_slot_link)

    async def _sync_image_links(self, game: Game, data: SubmitGameForm, image_loader: ImageLoader) -> None:
        # Images
        desired_image_ids_or_images = [
            image if isinstance(image, int) else await self.create_image(image, image_loader) for image in data.image
        ]
        # Remove any image links that are not in the desired list
        for image_link in game.image_links:
            if image_link.image_id not in desired_image_ids_or_images:
                await self._session.delete(image_link)
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
            self._session.add(image_link)

    async def set_submission_status(self, game: Game, submission_status: SubmissionStatus) -> Game:
        game.submission_status = submission_status
        self._session.add(game)
        return game

    async def get_game_for_detail(self, game_id: int) -> Game | None:
        """Load a Game with the associations needed to render the game detail page."""
        return (
            await self._session.execute(
                select(Game)
                .options(
                    selectinload(Game.system),
                    selectinload(Game.gamemaster),
                    selectinload(Game.event),
                    selectinload(Game.game_requirement),
                    selectinload(Game.genres),
                    selectinload(Game.content_warnings),
                    selectinload(Game.images),
                )
                .where(Game.id == game_id)
            )
        ).scalar_one_or_none()

    async def get_user_game_context(self, *, game_id: int, user_id: int, event_id: int) -> UserGameContext:
        """Look up the requesting user's preference, play history, and d20 balance for a game."""
        user_game_preference = (
            await self._session.execute(
                select(UserGamePreference).where(
                    UserGamePreference.game_id == game_id,
                    UserGamePreference.user_id == user_id,
                    UserGamePreference.frozen_at_time_slot_id.is_(None),
                )
            )
        ).scalar_one_or_none()
        preference = user_game_preference.preference if user_game_preference else None

        latest_d20_transaction = (
            await self._session.execute(
                select(UserEventD20Transaction)
                .where(UserEventD20Transaction.user_id == user_id)
                .where(UserEventD20Transaction.event_id == event_id)
                .order_by(UserEventD20Transaction.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

        user_game_played = (
            await self._session.execute(
                select(UserGamePlayed).where(UserGamePlayed.user_id == user_id, UserGamePlayed.game_id == game_id)
            )
        ).scalar_one_or_none()

        return UserGameContext(
            preference=preference,
            user_game_played=user_game_played,
            has_d20=latest_d20_transaction is not None and latest_d20_transaction.current_balance > 0,
        )

    async def get_scheduled_sessions(self, game_id: int) -> list[Session]:
        """Return a game's committed sessions, ordered by their time slot's start time."""
        scheduled_sessions = (
            (
                await self._session.execute(
                    select(Session)
                    .where(
                        Session.game_id == game_id,
                        Session.committed,
                    )
                    .options(
                        selectinload(Session.table).selectinload(Table.room),
                        selectinload(Session.time_slot),
                    )
                )
            )
            .scalars()
            .all()
        )
        return sorted(scheduled_sessions, key=lambda s: s.time_slot.start_time)

    async def get_game_image_urls(self, game: Game, image_loader: ImageLoader) -> list[dict[str, str]]:
        """Build full and thumbnail URLs for a game's images."""
        return [
            {
                "full": await image_loader.get_image_path(image.lookup_key),
                "thumbnail": await image_loader.get_image_path(image.lookup_key, size=300),
            }
            for image in game.images
        ]


async def provide_game_service(transaction: AsyncSession) -> GameService:
    return GameService(transaction)
