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
# Convergence 2024

I could put in a bunch of info here, but it's not important for now. This will be a sick landing/home page eventually.

## TODO - More content

- Bullet points
- Wow
"""
    return page(c.Markdown(text=markdown))


@router.get("/{path:path}", status_code=404)
async def api_404():
    # so we don't fall through to the index page
    return {"message": "Not Found"}
