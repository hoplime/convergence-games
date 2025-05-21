from abc import ABC, abstractmethod
from uuid import UUID


class ImageLoader(ABC):
    @abstractmethod
    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        """Saves the image to the storage."""
        pass

    @abstractmethod
    async def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        pass
