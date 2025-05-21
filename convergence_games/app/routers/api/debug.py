from typing import Annotated
from uuid import uuid4

from litestar import Controller, Response, post
from litestar.datastructures import UploadFile
from litestar.enums import RequestEncodingType
from litestar.params import Body
from litestar.status_codes import HTTP_204_NO_CONTENT
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.create_mock_data import create_mock_data
from convergence_games.services import ImageLoader


class DebugController(Controller):
    @post(path="/create_mock_data")
    async def create_mock_data(self, transaction: AsyncSession) -> Response:
        await create_mock_data(transaction)
        return Response(content="", status_code=HTTP_204_NO_CONTENT)

    @post(path="/upload_image")
    async def upload_image(
        self, data: Annotated[UploadFile, Body(media_type=RequestEncodingType.MULTI_PART)], image_loader: ImageLoader
    ) -> Response:
        image_data = await data.read()
        lookup = uuid4()
        await image_loader.save_image(image_data, lookup)
        return Response(content=await image_loader.get_image_path(lookup))
