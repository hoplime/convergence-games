import pytest
from litestar.datastructures import UploadFile

from convergence_games.app.routers.frontend.submit_game import _validate_image_uploads
from convergence_games.settings import SETTINGS


def _upload(name: str, content_type: str) -> UploadFile:
    return UploadFile(content_type=content_type, filename=name, file_data=b"\x00")


def test_accepts_valid_image_list() -> None:
    images = [_upload("a.png", "image/png"), _upload("b.jpg", "image/jpeg")]
    assert _validate_image_uploads(images) is images


def test_accepts_existing_image_ids_alongside_uploads() -> None:
    images: list[UploadFile | int] = [42, _upload("a.png", "image/png")]
    assert _validate_image_uploads(images) is images


def test_rejects_too_many_images() -> None:
    over = SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME + 1
    images = [_upload(f"{i}.png", "image/png") for i in range(over)]
    with pytest.raises(ValueError, match=f"at most {SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME}"):
        _validate_image_uploads(images)


def test_rejects_disallowed_mime_type() -> None:
    images = [_upload("evil.svg", "image/svg+xml")]
    with pytest.raises(ValueError, match="Image 1: type 'image/svg\\+xml' is not supported"):
        _validate_image_uploads(images)


def test_message_uses_one_based_index_for_offending_image() -> None:
    images = [
        _upload("a.png", "image/png"),
        _upload("b.png", "image/png"),
        _upload("c.svg", "image/svg+xml"),
    ]
    with pytest.raises(ValueError, match="Image 3: type 'image/svg\\+xml'"):
        _validate_image_uploads(images)


def test_collects_multiple_errors_into_one_message() -> None:
    over = SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME + 1
    images = [_upload(f"{i}.svg", "image/svg+xml") for i in range(over)]
    with pytest.raises(ValueError) as excinfo:
        _validate_image_uploads(images)
    message = str(excinfo.value)
    assert f"at most {SETTINGS.IMAGE_UPLOAD_MAX_IMAGES_PER_GAME}" in message
    assert "Image 1:" in message
