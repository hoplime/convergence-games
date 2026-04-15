"""Tests for the FAQ markdown → Jinja build script."""

from scripts.build_faq import build_page, main, parse_markdown


def test_section_heading_renders_with_size_class() -> None:
    out = parse_markdown("## Section\n")
    assert '<h2 class="text-xl">Section</h2>' in out


def test_question_with_anchor_opens_collapse() -> None:
    src = "{#society-member}\n### Do I get perks?\n\nYes.\n"
    out = parse_markdown(src)
    assert '<Collapse class="collapse-plus border border-base-300 bg-base-100">' in out
    assert '<h3 id="society-member">Do I get perks?</h3>' in out
    assert "<p>Yes.</p>" in out
    # Collapse closes at EOF.
    assert out.rstrip().endswith("</Collapse>")


def test_consecutive_questions_close_prior_collapse() -> None:
    src = "{#a}\n### First\n\nOne.\n\n{#b}\n### Second\n\nTwo.\n"
    out = parse_markdown(src)
    # Exactly two open + two close collapses.
    assert out.count("<Collapse ") == 2
    assert out.count("</Collapse>") == 2
    # Order: first opens, closes, second opens, closes.
    first_close = out.index("</Collapse>")
    second_open = out.index('id="b"')
    assert first_close < second_open


def test_section_heading_closes_prior_collapse() -> None:
    src = "{#a}\n### Q\n\nBody.\n\n## New Section\n"
    out = parse_markdown(src)
    assert out.index("</Collapse>") < out.index("<h2")


def test_bullet_list_gets_injected_classes() -> None:
    src = "## S\n\n- alpha\n- beta\n"
    out = parse_markdown(src)
    assert '<ul class="flex list-disc flex-col gap-2 pl-4">' in out
    assert "<li>alpha\n</li>" in out
    assert "<li>beta\n</li>" in out
    # Tight list — no <p> wrapper inside <li>.
    assert "<li><p>" not in out


def test_markdown_link_becomes_l_component() -> None:
    out = parse_markdown("## S\n\nSee [the docs](https://example.com/docs).\n")
    assert '<L href="https://example.com/docs">the docs</L>' in out


def test_inline_raw_html_passes_through() -> None:
    src = '## S\n\n- item <Tooltip align="top"><label>hover</label><TooltipContent>detail</TooltipContent></Tooltip>\n'
    out = parse_markdown(src)
    assert '<Tooltip align="top">' in out
    assert "<TooltipContent>detail</TooltipContent>" in out


def test_jinja_interpolation_survives() -> None:
    src = '## S\n\n<L href="/x/{{ SETTINGS.FOO }}/y">go</L>\n'
    out = parse_markdown(src)
    assert "{{ SETTINGS.FOO }}" in out
    # Must not have been percent-encoded.
    assert "%7B%7B" not in out


def test_build_page_wraps_body_in_shell() -> None:
    page = build_page("<p>hi</p>\n")
    assert page.startswith("{# GENERATED FROM faq.md")
    assert "<PageTitle>FAQ</PageTitle>" in page
    assert '<h1 class="text-xl">Frequently Asked Questions</h1>' in page
    assert "<p>hi</p>" in page
    assert page.rstrip().endswith("</Page>")


def test_check_mode_matches_committed_output() -> None:
    """Re-running the build against committed faq.md must produce the committed
    faq.html.jinja byte-for-byte. Guards against drift between source and output."""
    assert main(["--check"]) == 0, "faq.html.jinja is out of date — run scripts/build_faq.py"
