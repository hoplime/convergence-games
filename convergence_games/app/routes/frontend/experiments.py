from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from convergence_games.app.templates import templates

router = APIRouter()


@router.get("/test_page")
async def test_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("components/TestPage.html.jinja", {"request": request})
