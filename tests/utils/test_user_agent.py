from convergence_games.utils.user_agent import format_user_agent, parse_user_agent


def test_chrome_on_macos() -> None:
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    assert parse_user_agent(ua) == ("Chrome", "macOS")


def test_firefox_on_windows() -> None:
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0"
    assert parse_user_agent(ua) == ("Firefox", "Windows")


def test_safari_on_macos() -> None:
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    )
    assert parse_user_agent(ua) == ("Safari", "macOS")


def test_edge_on_windows() -> None:
    ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0"
    )
    assert parse_user_agent(ua) == ("Edge", "Windows")


def test_chrome_on_linux() -> None:
    ua = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    assert parse_user_agent(ua) == ("Chrome", "Linux")


def test_chrome_on_android() -> None:
    ua = (
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
    )
    assert parse_user_agent(ua) == ("Chrome", "Android")


def test_safari_on_ios() -> None:
    ua = (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    assert parse_user_agent(ua) == ("Safari", "iOS")


def test_safari_on_ipados() -> None:
    ua = (
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    )
    assert parse_user_agent(ua) == ("Safari", "iPadOS")


def test_opera() -> None:
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 OPR/106.0.0.0"
    )
    assert parse_user_agent(ua) == ("Opera", "macOS")


def test_unknown_returns_fallback() -> None:
    assert parse_user_agent("totally-unrecognised-string") == ("Browser", "Unknown")


def test_none_returns_unknowns() -> None:
    assert parse_user_agent(None) == ("Unknown", "Unknown")


def test_empty_returns_unknowns() -> None:
    assert parse_user_agent("") == ("Unknown", "Unknown")


def test_format_user_agent() -> None:
    ua = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    assert format_user_agent(ua) == "Chrome on macOS"


def test_format_user_agent_none() -> None:
    assert format_user_agent(None) == "Unknown on Unknown"
