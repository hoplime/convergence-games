from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from convergence_games.app.templates import templates

router = APIRouter(tags=["frontend"])


@router.get("/")
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="index.html.jinja")
