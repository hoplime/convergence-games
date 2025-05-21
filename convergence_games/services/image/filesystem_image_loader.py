import asyncio
from io import BytesIO
from pathlib import Path
from typing import Sequence, override
from uuid import UUID, uuid4

from aiofiles import open as aio_open
from PIL import Image as PILImage

from .image_loader import ImageLoader


def create_subfolder_for_guid(lookup: UUID) -> Sequence[str]:
    lookup_str = str(lookup)
    return lookup_str[:2], lookup_str[2:4], lookup_str[4:6]


class FilesystemImageLoader(ImageLoader):
    def __init__(self, base_path: Path, pre_cache_sizes: list[int] | None = None) -> None:
        self._base_path = base_path
        self._pre_cache_sizes = pre_cache_sizes or []

    async def _write_image(self, image: PILImage.Image, path: Path, thumbnail_size: int | None = None) -> None:
        output = BytesIO()

        if thumbnail_size is not None:
            image = image.copy()
            image.thumbnail((thumbnail_size, thumbnail_size))

        image.save(output, format="JPEG")

        async with aio_open(path, "wb") as f:
            await f.write(output.getvalue())

    @override
    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        """Saves the image to the storage."""
        path = self._base_path.joinpath(*create_subfolder_for_guid(lookup))
        path.mkdir(parents=True, exist_ok=True)

        # Save the image to the original path
        # This is technically synchronous, but it is writing to memory
        image = PILImage.open(BytesIO(image_data))
        await self._write_image(image, path / f"{lookup}_full.jpg")

        # Save the image in different sizes
        for size in self._pre_cache_sizes:
            thumbnail_path = path / f"{lookup}_{size}.jpg"
            await self._write_image(image, thumbnail_path, thumbnail_size=size)

    @override
    async def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        path = self._base_path.joinpath(*create_subfolder_for_guid(lookup))

        if size is None:
            return str(path / f"{lookup}_full.jpg")

        thumbnail_path = path / f"{lookup}_{size}.jpg"

        if not thumbnail_path.exists():
            full_size_image = PILImage.open(path / f"{lookup}_full.jpg")
            await self._write_image(full_size_image, thumbnail_path, thumbnail_size=size)

        return str(thumbnail_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Filesystem Image Loader")
    parser.add_argument("base_path", type=Path, help="Base path for image storage")
    parser.add_argument("image_path", type=Path, help="Path to the image file")
    parser.add_argument(
        "--pre-cache-sizes",
        type=int,
        nargs="+",
        default=[150, 300],
        help="List of sizes to pre-cache",
    )
    args = parser.parse_args()

    # Example usage
    loader = FilesystemImageLoader(args.base_path, pre_cache_sizes=args.pre_cache_sizes)
    with open(args.image_path, "rb") as f:
        image_data = f.read()
    lookup = uuid4()

    asyncio.run(loader.save_image(image_data, lookup))
    print(f"Image saved with lookup: {lookup}")
    full_image_path = asyncio.run(loader.get_image_path(lookup))
    print(f"Full image path: {full_image_path}")
    thumbnail_image_path = asyncio.run(loader.get_image_path(lookup, size=150))
    print(f"Thumbnail image path: {thumbnail_image_path}")
    thumbnail_image_path = asyncio.run(loader.get_image_path(lookup, size=400))
    print(f"Thumbnail image path: {thumbnail_image_path}")
