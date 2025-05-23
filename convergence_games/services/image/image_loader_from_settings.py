from convergence_games.settings import SETTINGS

from .blob_image_loader import BlobImageLoader
from .filesystem_image_loader import FilesystemImageLoader
from .image_loader import ImageLoader


def _image_loader_from_settings() -> ImageLoader:
    if SETTINGS.IMAGE_STORAGE_MODE == "blob":
        assert SETTINGS.IMAGE_STORAGE_ACCOUNT_NAME is not None, (
            "IMAGE_STORAGE_ACCOUNT_NAME must be set if IMAGE_STORAGE_MODE is 'blob'."
        )
        assert SETTINGS.IMAGE_STORAGE_CONTAINER_NAME is not None, (
            "IMAGE_STORAGE_CONTAINER_NAME must be set if IMAGE_STORAGE_MODE is 'blob'."
        )
        image_loader = BlobImageLoader(
            storage_account_name=SETTINGS.IMAGE_STORAGE_ACCOUNT_NAME,
            container_name=SETTINGS.IMAGE_STORAGE_CONTAINER_NAME,
            pre_cache_sizes=SETTINGS.IMAGE_PRE_CACHE_SIZES,
        )
    else:
        assert SETTINGS.IMAGE_STORAGE_PATH is not None, (
            "IMAGE_STORAGE_PATH must be set if IMAGE_STORAGE_MODE is 'filesystem'."
        )
        image_loader = FilesystemImageLoader(
            base_path=SETTINGS.IMAGE_STORAGE_PATH,
            pre_cache_sizes=SETTINGS.IMAGE_PRE_CACHE_SIZES,
        )

    return image_loader


image_loader_from_settings = _image_loader_from_settings()
