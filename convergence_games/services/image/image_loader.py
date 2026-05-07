import warnings
from abc import ABC, abstractmethod
from io import BytesIO
from uuid import UUID

import PIL.Image as PILImage

from convergence_games.settings import SETTINGS


class ImageDecodeError(Exception):
    """Raised when image bytes cannot be safely decoded.

    Wraps unidentified formats, truncated/corrupt files, decompression bombs,
    and any other PIL/OS error encountered while opening or loading an image.
    """


class ImageLoader(ABC):
    def _decode_and_normalise(self, image_data: bytes) -> PILImage.Image:
        """Open image bytes safely and downscale to the configured maximum dimension.

        Forces a full decode (`image.load()`) so truncated files surface here
        rather than later. Images whose longest side exceeds
        `IMAGE_UPLOAD_MAX_DIMENSION_PIXELS` are downscaled in-place via
        `Image.thumbnail`.
        """
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", PILImage.DecompressionBombWarning)
                image = PILImage.open(BytesIO(image_data))
                image.load()
        except (
            PILImage.UnidentifiedImageError,
            PILImage.DecompressionBombError,
            PILImage.DecompressionBombWarning,
            OSError,
            ValueError,
        ) as exc:
            raise ImageDecodeError(str(exc)) from exc

        max_dim = SETTINGS.IMAGE_UPLOAD_MAX_DIMENSION_PIXELS
        if max(image.size) > max_dim:
            image.thumbnail((max_dim, max_dim))

        return image

    def _dump_to_bytes(self, image: PILImage.Image, thumbnail_size: int | None = None) -> bytes:
        output = BytesIO()

        if thumbnail_size is not None:
            image = image.copy()
            image.thumbnail((thumbnail_size, thumbnail_size))

        # Animated formats (e.g. GIF) are flattened to the first frame by `convert("RGB")`.
        image.convert("RGB").save(output, format="JPEG")
        return output.getvalue()

    @abstractmethod
    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        pass

    @abstractmethod
    async def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        pass
