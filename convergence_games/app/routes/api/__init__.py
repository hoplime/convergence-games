from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/")
async def index(request: Request) -> dict[str, str]:
    return {"message": "Hello World"}
