from io import BytesIO
from pathlib import Path
from typing import Sequence, override
from uuid import UUID, uuid4

from PIL import Image as PILImage

from .image_loader import ImageLoader


def create_subfolder_for_guid(lookup: UUID) -> Sequence[str]:
    lookup_str = str(lookup)
    return lookup_str[:2], lookup_str[2:4], lookup_str[4:6]


class FilesystemImageLoader(ImageLoader):
    def __init__(self, base_path: Path, pre_cache_sizes: list[int] | None = None) -> None:
        self._base_path = base_path
        self._pre_cache_sizes = pre_cache_sizes or []

    @override
    def save_image(self, image_data: bytes, lookup: UUID) -> None:
        """Saves the image to the storage."""
        path = self._base_path.joinpath(*create_subfolder_for_guid(lookup))
        path.mkdir(parents=True, exist_ok=True)

        # Save the image to the original path
        image = PILImage.open(BytesIO(image_data))
        image.save(path / f"{lookup}_full.jpg")

        # Save the image in different sizes
        for size in self._pre_cache_sizes:
            thumbnail_path = path / f"{lookup}_{size}.jpg"
            image_copy = image.copy()
            image_copy.thumbnail((size, size))
            image_copy.save(thumbnail_path, image.format)

    @override
    def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        path = self._base_path.joinpath(*create_subfolder_for_guid(lookup))

        if size is None:
            return str(path / f"{lookup}_full.jpg")

        thumbnail_path = path / f"{lookup}_{size}.jpg"

        if not thumbnail_path.exists():
            full_size_image = PILImage.open(path / f"{lookup}_full.jpg")
            image_copy = full_size_image.copy()
            image_copy.thumbnail((size, size))
            image_copy.save(thumbnail_path, full_size_image.format)

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
    loader.save_image(image_data, lookup)
    print(loader.get_image_path(lookup, size=150))
    print(loader.get_image_path(lookup, size=240))
