from __future__ import annotations as _annotations

from fastapi import APIRouter
from fastui import FastUI
from fastui import components as c

from ..common import page

router = APIRouter(prefix="/frontend")


@router.get("/", response_model_exclude_none=True)
def api_index() -> FastUI:
    # language=markdown
    markdown = """\
# BIG MARKDOWN ENERGY sdwafdagf
"""
    return page(c.Markdown(text=markdown))


@router.get("/{path:path}", status_code=404)
async def api_404():
    # so we don't fall through to the index page
    return {"message": "Not Found"}
