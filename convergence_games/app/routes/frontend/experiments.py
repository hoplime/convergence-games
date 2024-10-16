from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from convergence_games.app.dependencies import HxTarget
from convergence_games.app.templates import templates

router = APIRouter()


@router.get("/test_page_1")
async def test_page_1(request: Request, hx_target: HxTarget) -> HTMLResponse:
    return templates.TemplateResponse("pages/test_page_1.html.jinja", {"request": request}, block_name=hx_target)


@router.get("/test_page_2")
async def test_page_2(request: Request, hx_target: HxTarget) -> HTMLResponse:
    return templates.TemplateResponse("pages/test_page_2.html.jinja", {"request": request}, block_name=hx_target)
