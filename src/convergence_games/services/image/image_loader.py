from abc import ABC, abstractmethod
from io import BytesIO
from uuid import UUID

import PIL.Image as PILImage


class ImageLoader(ABC):
    def _dump_to_bytes(self, image: PILImage.Image, thumbnail_size: int | None = None) -> bytes:
        output = BytesIO()

        if thumbnail_size is not None:
            image = image.copy()
            image.thumbnail((thumbnail_size, thumbnail_size))

        image.convert("RGB").save(output, format="JPEG")
        return output.getvalue()

    @abstractmethod
    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        pass

    @abstractmethod
    async def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        pass
