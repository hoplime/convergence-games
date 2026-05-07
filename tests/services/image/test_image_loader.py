from io import BytesIO
from pathlib import Path
from uuid import uuid4

import PIL.Image as PILImage
import pytest

from convergence_games.services.image import FilesystemImageLoader, ImageDecodeError
from convergence_games.settings import SETTINGS


def _png_bytes(width: int, height: int) -> bytes:
    image = PILImage.new("RGB", (width, height), color=(120, 60, 200))
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def loader(tmp_path: Path) -> FilesystemImageLoader:
    return FilesystemImageLoader(base_path=tmp_path, static_relative_path=tmp_path)


def test_decode_normalises_valid_image(loader: FilesystemImageLoader) -> None:
    image = loader._decode_and_normalise(_png_bytes(100, 50))
    assert image.size == (100, 50)


def test_decode_rejects_garbage_bytes(loader: FilesystemImageLoader) -> None:
    with pytest.raises(ImageDecodeError):
        loader._decode_and_normalise(b"definitely not an image")


def test_decode_rejects_truncated_png(loader: FilesystemImageLoader) -> None:
    full = _png_bytes(40, 40)
    truncated = full[: len(full) // 2]
    with pytest.raises(ImageDecodeError):
        loader._decode_and_normalise(truncated)


def test_decode_rejects_decompression_bomb(loader: FilesystemImageLoader) -> None:
    cap = SETTINGS.IMAGE_UPLOAD_MAX_DECODE_PIXELS
    side = int(cap**0.5) + 1000
    bomb_bytes = _png_bytes(side, side)
    with pytest.raises(ImageDecodeError):
        loader._decode_and_normalise(bomb_bytes)


def test_decode_downscales_oversized_image(loader: FilesystemImageLoader) -> None:
    max_dim = SETTINGS.IMAGE_UPLOAD_MAX_DIMENSION_PIXELS
    oversize = max_dim + 1500
    image = loader._decode_and_normalise(_png_bytes(oversize, oversize // 2))
    assert max(image.size) <= max_dim


def test_decode_leaves_within_limit_image_alone(loader: FilesystemImageLoader) -> None:
    max_dim = SETTINGS.IMAGE_UPLOAD_MAX_DIMENSION_PIXELS
    image = loader._decode_and_normalise(_png_bytes(max_dim, max_dim // 2))
    assert image.size == (max_dim, max_dim // 2)


@pytest.mark.asyncio
async def test_save_image_persists_full_size_jpeg(loader: FilesystemImageLoader, tmp_path: Path) -> None:
    lookup = uuid4()
    await loader.save_image(_png_bytes(80, 60), lookup)

    saved_path = await loader.get_image_path(lookup)
    relative = saved_path.removeprefix("/static/")
    on_disk = tmp_path / relative
    assert on_disk.exists()
    saved_image = PILImage.open(on_disk)
    saved_image.load()
    assert saved_image.format == "JPEG"


@pytest.mark.asyncio
async def test_save_image_raises_on_corrupt_input(loader: FilesystemImageLoader) -> None:
    with pytest.raises(ImageDecodeError):
        await loader.save_image(b"not an image", uuid4())
