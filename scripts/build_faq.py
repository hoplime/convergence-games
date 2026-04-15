"""Build `faq.html.jinja` from `faq.md`.

The FAQ page is maintained as a single markdown file. This script parses
the markdown and emits the JinjaX template that the route handler
renders. Headers drive the structure:

- `##` opens a section heading
- `###` opens a collapse (closes on next same-or-higher heading or EOF)

Anchors are attached via block-attribute syntax on the line above a heading:

    {#society-member}
    ### Question text

The emitted HTML uses JinjaX components (`<L>`, `<Collapse>`, etc.) which
the template engine expands at request time. Inline JinjaX tags and
`{{ ... }}` expressions in the markdown source pass through verbatim.

Run:
    PYTHONPATH=. uv run python scripts/build_faq.py

Use `--check` in CI to fail on drift.
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.attrs import attrs_block_plugin

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = REPO_ROOT / "convergence_games/app/templates/pages/faq.md"
DEFAULT_OUTPUT = REPO_ROOT / "convergence_games/app/templates/pages/faq.html.jinja"

GENERATED_BANNER = (
    "{# GENERATED FROM faq.md — DO NOT EDIT DIRECTLY. #}\n{# Run: PYTHONPATH=. uv run python scripts/build_faq.py #}\n"
)


@dataclass
class CliArgs:
    input: Path
    output: Path
    check: bool


def _render_inline(token: Token) -> str:
    """Render an `inline` token's children to Jinja-compatible HTML."""
    assert token.children is not None
    out: list[str] = []
    for child in token.children:
        out.append(_render_inline_child(child))
    return "".join(out)


_INLINE_SIMPLE: dict[str, str] = {
    "softbreak": "\n",
    "hardbreak": "<br />\n",
    "em_open": "<i>",
    "em_close": "</i>",
    "strong_open": "<b>",
    "strong_close": "</b>",
    "s_open": "<s>",
    "s_close": "</s>",
    "link_close": "</L>",
}


def _render_inline_child(token: Token) -> str:
    t = token.type
    if t == "text":
        # Do not HTML-escape — `{{ ... }}` must survive for Jinja, and
        # inline angle-bracket JinjaX tags are already split into
        # `html_inline` tokens by the parser.
        return token.content
    if t == "code_inline":
        return f"<code>{token.content}</code>"
    if t == "link_open":
        href = token.attrGet("href") or ""
        return f'<L href="{href}">'
    if t == "html_inline":
        return token.content
    simple = _INLINE_SIMPLE.get(t)
    if simple is not None:
        return simple
    raise ValueError(f"Unsupported inline token: {t}")


_BLOCK_SIMPLE: dict[str, str] = {
    "bullet_list_open": '<ul class="flex list-disc flex-col gap-2 pl-4">\n',
    "bullet_list_close": "</ul>\n",
    "ordered_list_open": '<ol class="flex list-decimal flex-col gap-2 pl-4">\n',
    "ordered_list_close": "</ol>\n",
    "list_item_open": "<li>",
    "list_item_close": "</li>\n",
}


def _render_heading(tokens: list[Token], i: int, in_collapse: bool) -> tuple[str, int, bool]:
    """Render a heading + its inline content. Returns (html, next_i, in_collapse)."""
    tok = tokens[i]
    level = int(tok.tag[1:])
    anchor = tok.attrGet("id")
    inline_html = _render_inline(tokens[i + 1])
    next_i = i + 3  # heading_open, inline, heading_close

    # Any new heading closes a previously-open collapse.
    prefix = "</CollapseContent>\n</Collapse>\n" if in_collapse else ""
    in_collapse = False

    if level == 1:
        # Page title handled by the <PageTitle> shell.
        return prefix, next_i, in_collapse
    if level == 2:
        return f'{prefix}<h2 class="text-xl">{inline_html}</h2>\n', next_i, in_collapse
    if level == 3:
        id_attr = f' id="{anchor}"' if anchor else ""
        html = (
            f"{prefix}"
            '<Collapse class="collapse-plus border border-base-300 bg-base-100">\n'
            '<input type="checkbox" />\n'
            '<CollapseTitle class="font-semibold">\n'
            f"<h3{id_attr}>{inline_html}</h3>\n"
            "</CollapseTitle>\n"
            '<CollapseContent class="flex flex-col gap-2">\n'
        )
        return html, next_i, True

    id_attr = f' id="{anchor}"' if anchor else ""
    return f"{prefix}<h{level}{id_attr}>{inline_html}</h{level}>\n", next_i, in_collapse


def _render_tokens(tokens: list[Token]) -> str:
    out: list[str] = []
    in_collapse = False
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        t = tok.type

        if t == "heading_open":
            html, i, in_collapse = _render_heading(tokens, i, in_collapse)
            out.append(html)
            continue

        if t == "paragraph_open":
            inline_html = _render_inline(tokens[i + 1])
            # Tight-list items mark their wrapping paragraph as hidden —
            # match the default HTML renderer and skip the <p> wrapper.
            if tok.hidden:
                out.append(f"{inline_html}\n")
            else:
                out.append(f"<p>{inline_html}</p>\n")
            i += 3
            continue

        simple = _BLOCK_SIMPLE.get(t)
        if simple is not None:
            out.append(simple)
            i += 1
            continue

        if t == "html_block":
            out.append(tok.content)
            i += 1
            continue

        # attrs_block tokens and other containers have no direct output.
        i += 1

    if in_collapse:
        out.append("</CollapseContent>\n</Collapse>\n")
    return "".join(out)


def parse_markdown(src: str) -> str:
    """Convert FAQ markdown source to a Jinja body fragment."""
    md = MarkdownIt("commonmark", {"html": True}).use(attrs_block_plugin)
    tokens = md.parse(src)
    return _render_tokens(tokens)


def build_page(body: str) -> str:
    """Wrap a rendered body fragment in the static page shell."""
    indented_lines = ("                " + line if line.strip() else "" for line in body.splitlines())
    indented = "\n".join(indented_lines)
    return (
        f"{GENERATED_BANNER}"
        "<Page>\n"
        "    {% block content %}\n"
        "        <PageTitle>FAQ</PageTitle>\n"
        "        <PageContainer>\n"
        '            <div class="flex flex-col gap-4">\n'
        '                <h1 class="text-xl">Frequently Asked Questions</h1>\n'
        f"{indented}\n"
        "            </div>\n"
        "        </PageContainer>\n"
        "    {% endblock %}\n"
        "</Page>\n"
    )


def _parse_args(argv: list[str] | None) -> CliArgs:
    parser = argparse.ArgumentParser(description="Build faq.html.jinja from faq.md.")
    _ = parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Source markdown path.")
    _ = parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Target Jinja template path.")
    _ = parser.add_argument("--check", action="store_true", help="Exit non-zero if the target file would change.")
    ns = parser.parse_args(argv)
    return CliArgs(input=ns.input, output=ns.output, check=ns.check)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    src = args.input.read_text(encoding="utf-8")
    rendered = build_page(parse_markdown(src))

    if args.check:
        existing = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        if existing != rendered:
            print(f"{args.output} is out of date. Run scripts/build_faq.py.", file=sys.stderr)
            return 1
        return 0

    _ = args.output.write_text(rendered, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
