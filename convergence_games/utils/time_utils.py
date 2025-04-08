import datetime as dt
import zoneinfo
from typing import Literal


def nice_time_format(
    date: dt.datetime, tz: str | dt.tzinfo | None = None, mode: Literal["long", "short"] = "short"
) -> str:
    if tz is None:
        tz = zoneinfo.ZoneInfo("Pacific/Auckland")
    elif isinstance(tz, str):
        tz = zoneinfo.ZoneInfo(tz)
    elif not isinstance(tz, zoneinfo.ZoneInfo):
        raise TypeError(f"Expected str or zoneinfo.ZoneInfo, got {type(tz)}")

    return date.astimezone(tz).strftime("%a %B %d %I:%M%p %Z" if mode == "long" else "%a %b %d %I:%M%p %Z")
