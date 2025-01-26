from litestar import Controller, Response, post
from litestar.status_codes import HTTP_204_NO_CONTENT
from sqlalchemy.ext.asyncio import AsyncSession

from convergence_games.db.create_mock_data import create_mock_data


class DebugController(Controller):
    @post(path="/create_mock_data")
    async def create_mock_data(self, db_session: AsyncSession) -> Response:
        await create_mock_data(db_session)
        return Response(content="", status_code=HTTP_204_NO_CONTENT)
