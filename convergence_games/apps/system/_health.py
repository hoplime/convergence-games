from litestar import get
from litestar.response import Response


@get("/health", include_in_schema=False)
async def health_check() -> Response[dict[str, str]]:
    return Response(content={"status": "ok"}, status_code=200)
