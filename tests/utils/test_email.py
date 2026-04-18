from convergence_games.utils.email import normalize_email


def test_lowercase() -> None:
    assert normalize_email("Foo@Example.COM") == "foo@example.com"


def test_strip_whitespace() -> None:
    assert normalize_email("  foo@example.com  ") == "foo@example.com"


def test_strip_and_lowercase() -> None:
    assert normalize_email("  Foo@Example.COM  ") == "foo@example.com"


def test_already_normalized() -> None:
    assert normalize_email("foo@example.com") == "foo@example.com"


def test_empty_string() -> None:
    assert normalize_email("") == ""


def test_only_whitespace() -> None:
    assert normalize_email("   ") == ""
