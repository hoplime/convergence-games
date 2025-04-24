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


def time_range_format(
    start: dt.datetime,
    end: dt.datetime,
    tz: str | dt.tzinfo | None = None,
    mode: Literal["long", "short"] = "short",
) -> str:
    if tz is None:
        tz = zoneinfo.ZoneInfo("Pacific/Auckland")
    elif isinstance(tz, str):
        tz = zoneinfo.ZoneInfo(tz)
    elif not isinstance(tz, zoneinfo.ZoneInfo):
        raise TypeError(f"Expected str or zoneinfo.ZoneInfo, got {type(tz)}")

    start = start.astimezone(tz)
    end = end.astimezone(tz)
    is_start_same_day = start.date() == end.date()

    start_str = start.strftime("%a %B %d %I:%M%p" if mode == "long" else "%a %b %d %I:%M%p")
    end_str = (
        end.strftime("%I:%M%p %Z")
        if is_start_same_day
        else end.strftime("%a %B %d %I:%M%p %Z" if mode == "long" else "%a %b %d %I:%M%p %Z")
    )
    return f"{start_str} - {end_str}"
