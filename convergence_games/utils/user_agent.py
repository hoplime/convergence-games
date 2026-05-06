"""Coarse User-Agent parser for the sessions UI.

We only need a "browser / OS" string to help users recognise their own sessions; we don't try
to compete with full UA-parsing libraries. Order of regex matching matters because some UA
strings contain multiple browser tokens (e.g. Edge UA contains 'Chrome' and 'Safari').
"""

import re

# Browser detection — order matters: more specific tokens (Edge, OPR/Opera) before
# generic Chrome/Safari which they pretend to be.
_BROWSER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Edge", re.compile(r"Edg(e|A|iOS)?/", re.IGNORECASE)),
    ("Opera", re.compile(r"(OPR|Opera)/", re.IGNORECASE)),
    ("Firefox", re.compile(r"Firefox/", re.IGNORECASE)),
    ("Chrome", re.compile(r"Chrome/", re.IGNORECASE)),
    ("Safari", re.compile(r"Safari/", re.IGNORECASE)),
]

# OS detection — also order-sensitive: iOS/iPadOS before macOS, Android before Linux.
_OS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("iPadOS", re.compile(r"iPad", re.IGNORECASE)),
    ("iOS", re.compile(r"iPhone|iPod", re.IGNORECASE)),
    ("Android", re.compile(r"Android", re.IGNORECASE)),
    ("Windows", re.compile(r"Windows NT", re.IGNORECASE)),
    ("macOS", re.compile(r"Macintosh|Mac OS X", re.IGNORECASE)),
    ("Linux", re.compile(r"Linux", re.IGNORECASE)),
]


def parse_user_agent(ua: str | None) -> tuple[str, str]:
    """Return a coarse (browser, os) tuple. Falls back to ('Unknown', 'Unknown') for empty input."""
    if not ua:
        return ("Unknown", "Unknown")

    browser = next((name for name, pattern in _BROWSER_PATTERNS if pattern.search(ua)), "Browser")
    os_name = next((name for name, pattern in _OS_PATTERNS if pattern.search(ua)), "Unknown")
    return (browser, os_name)


def format_user_agent(ua: str | None) -> str:
    """Render a user-friendly 'Browser on OS' string for templates."""
    browser, os_name = parse_user_agent(ua)
    return f"{browser} on {os_name}"
