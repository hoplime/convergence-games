from io import BytesIO
from typing import override
from uuid import UUID

import PIL.Image as PILImage
from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

from .common import subfolder_names_for_guid
from .image_loader import ImageLoader


class BlobImageLoader(ImageLoader):
    def __init__(
        self,
        storage_account_name: str,
        container_name: str,
        pre_cache_sizes: list[int] | None = None,
    ) -> None:
        self._blob_account_url = f"https://{storage_account_name}.blob.core.windows.net"
        self._container_name = container_name
        self._pre_cache_sizes = pre_cache_sizes or []

    @property
    def _blob_service_client(self) -> BlobServiceClient:
        return BlobServiceClient(
            account_url=self._blob_account_url,
            credential=DefaultAzureCredential(),
        )

    @override
    async def save_image(self, image_data: bytes, lookup: UUID) -> None:
        image = PILImage.open(BytesIO(image_data))

        async with self._blob_service_client as service_client:
            blob_path = "/".join(subfolder_names_for_guid(lookup))

            # Save the image to the original path
            blob_client = service_client.get_blob_client(self._container_name, f"{blob_path}/{lookup}_full.jpg")
            await blob_client.upload_blob(self._dump_to_bytes(image), overwrite=True)

            # Save the image in different sizes
            for size in self._pre_cache_sizes:
                blob_client = service_client.get_blob_client(self._container_name, f"{blob_path}/{lookup}_{size}.jpg")
                await blob_client.upload_blob(self._dump_to_bytes(image, thumbnail_size=size), overwrite=True)

    @override
    async def get_image_path(self, lookup: UUID, size: int | None = None) -> str:
        blob_path = "/".join(subfolder_names_for_guid(lookup))

        if size is None:
            return f"{self._blob_account_url}/{self._container_name}/{blob_path}/{lookup}_full.jpg"

        thumbnail_blob_path = f"{blob_path}/{lookup}_{size}.jpg"

        async with self._blob_service_client as service_client:
            blob_client = service_client.get_blob_client(self._container_name, thumbnail_blob_path)
            if not await blob_client.exists():
                full_size_blob_client = service_client.get_blob_client(
                    self._container_name, f"{blob_path}/{lookup}_full.jpg"
                )
                if await full_size_blob_client.exists():
                    full_size_image = await full_size_blob_client.download_blob()
                    image_data = await full_size_image.readall()
                    image = PILImage.open(BytesIO(image_data))
                    await blob_client.upload_blob(self._dump_to_bytes(image, thumbnail_size=size), overwrite=True)

                # If the full size image doesn't exist, we can't create the thumbnail, we just silently return the expected path

        return f"{self._blob_account_url}/{self._container_name}/{thumbnail_blob_path}"


if __name__ == "__main__":
    import argparse
    import asyncio
    from pathlib import Path
    from uuid import uuid4

    parser = argparse.ArgumentParser(description="Filesystem Image Loader")
    parser.add_argument("storage_account_name", type=str, help="Storage account name")
    parser.add_argument("container_name", type=str, help="Container name")
    parser.add_argument("image_path", type=Path, help="Path to the image file")
    parser.add_argument(
        "--pre-cache-sizes",
        type=int,
        nargs="+",
        default=[150, 300],
        help="List of sizes to pre-cache",
    )
    args = parser.parse_args()

    # Example BlobImageLoader
    loader = BlobImageLoader(args.storage_account_name, args.container_name, pre_cache_sizes=args.pre_cache_sizes)
    with open(args.image_path, "rb") as f:
        image_data = f.read()
    lookup = uuid4()

    asyncio.run(loader.save_image(image_data, lookup))
    print(f"Image saved with lookup: {lookup}")
