from functools import cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from fastui import FastUI
from fastui import components as c
from fastui.components.display import DisplayLookup, DisplayMode
from fastui.events import GoToEvent, PageEvent
from fastui.forms import SelectSearchResponse, fastui_form
from pydantic import BaseModel, Field
from sqlmodel import select

from convergence_games.app.common import page
from convergence_games.app.dependencies import SessionDependency
from convergence_games.app.extra_models import GameWithExtra, TableAllocationWithSlot
from convergence_games.db.extra_types import GameCrunch
from convergence_games.db.models import (
    Game,
    Genre,
    System,
    TimeSlot,
)

router = APIRouter(prefix="/frontend/sessions")


@router.get("", response_model_exclude_none=True)
async def get_games_view(
    *,
    session: SessionDependency,
) -> FastUI:
    return page(c.Heading(text="TODO Session Preferences List"), title="Session Preferences")
