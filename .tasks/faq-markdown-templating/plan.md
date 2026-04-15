---
title: FAQ markdown templating
created: 2026-04-15
status: complete
---

# FAQ markdown templating

## Context

`convergence_games/app/templates/pages/faq.html.jinja` is ~490 lines of
repeated `collapse-plus` / `collapse-title` / `collapse-content` markup
wrapping 22 FAQ entries across 4 sections (General, Ticket, GM, Player).
Non-developers who own the FAQ copy realistically cannot edit this file —
one wrong `</div>` and the page breaks.

Goal: move FAQ content into a single markdown source file that a
non-developer can edit, and generate the Jinja template from it with a
build script. Headers drive the structure:

- `##` → section heading
- `###` → question (opens a collapse, closes on next `##`/`###`/EOF)
- Everything else (paragraphs, lists, inline HTML/JinjaX) becomes the
  collapse body

Rich features needed in the copy are preserved by treating the rendered
HTML as a Jinja template:

- `<L href="...">` components for links
- `<Tooltip>` component (used on the Golden D20 reward)
- `{{ SETTINGS.DEFAULT_EVENT_SQID }}` interpolation in the "preferences"
  entry
- Anchor IDs on `<h3>` tags (e.g. `#society-member`, `#refunds`)

No runtime parsing — the generated `faq.html.jinja` is committed.

## Requirements

- Single source file `convergence_games/app/templates/pages/faq.md` owns
  all FAQ copy.
- Build script converts `faq.md` → `faq.html.jinja`. Output file is
  committed and served directly by the existing route handler.
- Generated file carries a header comment warning editors not to hand-edit.
- `###` headers with `{#anchor}` attribute extension produce `<h3 id="anchor">`
  inside a `<Collapse>` block; implicit collapse close happens at the next
  same-or-higher header or EOF.
- `##` headers render as styled section headings between collapse groups.
- Unordered lists get `flex list-disc flex-col gap-2 pl-4` classes injected
  so they match current visual output.
- Markdown link syntax `[text](url)` maps to the `<L href="url">text</L>`
  JinjaX component (not raw `<a>`).
- Raw inline HTML / JinjaX components in markdown pass through verbatim so
  `<Tooltip>`, `<b>`, `<i>` still work.
- `{{ ... }}` Jinja interpolation inside markdown survives to the generated
  file.
- Markdown parser is a **dev-only** dependency; runtime app has no new deps.
- Running the script is idempotent: running twice with no `.md` changes
  produces a byte-identical output file.
- Generated page is visually and structurally equivalent to the current
  `/faq` page — all 22 entries, same section order, same anchor IDs.

## Technical Design

### Files touched

| Path | Change |
| --- | --- |
| `pyproject.toml` | Add `markdown-it-py` and `mdit-py-plugins` to the dev group |
| `scripts/build_faq.py` | New — the build script (argparse CLI) |
| `convergence_games/app/templates/pages/faq.md` | New — source content |
| `convergence_games/app/templates/pages/faq.html.jinja` | Overwritten, now generated |
| `tests/scripts/test_build_faq.py` | New — renderer unit tests |
| `README.md` | Add note under a "Content editing" section pointing at `faq.md` + how to rebuild |

### Markdown source shape

```markdown
# Frequently Asked Questions

## General Questions

### I am a society member, what does that get me? {#society-member}

For a simple $10 a year you get access to pre-sales and the sought-after
Golden D20. ...

[Membership Registration Form](https://forms.gle/8Qraftky6WtTMxoT9)

### What can't I bring to the event? {#cant-bring}

Please do not bring any weapons, replica weapons or alcohol.

## Ticket Questions

### When are tickets available? {#attendance}
...
```

The top-level `#` is optional — the script does not rely on it; the page
title is still emitted by the JinjaX shell via `<PageTitle>`.

### Renderer (token-stream walker)

Parse with `markdown-it-py` using `MarkdownIt("commonmark")` plus the
`attrs_block` plugin from `mdit-py-plugins` for the `{#id}` extension.

Walk the flat token stream, tracking a single piece of state —
`in_collapse: bool` — and emit Jinja fragment strings to a buffer. Close
any open collapse on `heading_open` for levels `<= 3` or at EOF.

Token → output mapping:

| Token | Emission |
| --- | --- |
| `heading_open` `h1` | Skip — page title handled by `<PageTitle>` shell |
| `heading_open` `h2` | `<h2 class="text-xl">` |
| `heading_close` `h2` | `</h2>` |
| `heading_open` `h3` (with `{#id}`) | Close prior collapse if open; `<Collapse class="collapse-plus border border-base-300 bg-base-100"><input type="checkbox" /><CollapseTitle class="font-semibold"><h3 id="{id}">` |
| `heading_close` `h3` | `</h3></CollapseTitle><CollapseContent class="flex flex-col gap-2">` |
| `paragraph_open/close` | `<p>` / `</p>` |
| `bullet_list_open` | `<ul class="flex list-disc flex-col gap-2 pl-4">` |
| `bullet_list_close` | `</ul>` |
| `list_item_open/close` | `<li>` / `</li>` |
| `link_open` | `<L href="{href}">` |
| `link_close` | `</L>` |
| `em`, `strong`, `s` etc. | `<i>` / `<b>` / `<s>` as per standard mapping |
| `html_inline`, `html_block` | Passthrough verbatim (so `<Tooltip>` etc. survive) |
| `text` | Verbatim text — **no** HTML escaping of `{` / `}` so Jinja interpolation survives |
| EOF | Close any trailing collapse |

Final output wrapped in the existing page shell:

```jinja
{# GENERATED FROM faq.md — DO NOT EDIT DIRECTLY. #}
{# Run: PYTHONPATH=. uv run python scripts/build_faq.py #}
<Page>
    {% block content %}
        <PageTitle>FAQ</PageTitle>
        <PageContainer>
            <div class="flex flex-col gap-4">
                <h1 class="text-xl">Frequently Asked Questions</h1>
                {{ rendered_body }}
            </div>
        </PageContainer>
    {% endblock %}
</Page>
```

### Script CLI

`scripts/build_faq.py` uses `argparse` (per `.claude/rules/python-style.md`):

- `--check` — exits non-zero if the generated file would change (for CI)
- `--input` / `--output` — overridable paths for tests
- No args → regenerate `faq.html.jinja` from `faq.md` in place

Run invocation matches the project's script convention
(`PYTHONPATH=. uv run python scripts/build_faq.py`, per memory).

### Dependencies

Add to `[dependency-groups].dev` in `pyproject.toml`:

- `markdown-it-py`
- `mdit-py-plugins`

Runtime install (`uv sync --no-dev`) gets nothing new.

### Route handler

`convergence_games/app/routers/frontend/home.py::HomeController.get_faq`
is **unchanged** — still renders `pages/faq.html.jinja`.

## Implementation Plan

### Phase 1: Deps & builder skeleton

- [x] **Add markdown deps** (`pyproject.toml`)
  - Add `markdown-it-py`, `mdit-py-plugins` under a `dev` dependency group
  - `uv sync`
- [x] **Create renderer module** (`scripts/build_faq.py`)
  - `argparse` CLI: `--input`, `--output`, `--check`
  - `parse_markdown(src: str) -> str` returns the Jinja body fragment
  - `build_page(body: str) -> str` wraps in the `<Page>` shell + header comment
  - Separate pure-function renderer from file I/O so tests can hit `parse_markdown` directly

#### Phase 1 verification

- [x] `basedpyright` — no new errors
- [x] `ruff check` — no new errors
- [x] `PYTHONPATH=. uv run python scripts/build_faq.py --help` prints usage

### Phase 2: Content migration

- [x] **Write `faq.md`** (`convergence_games/app/templates/pages/faq.md`)
  - Port all 22 entries under their 4 `##` sections
  - Preserve existing anchors via `{#id}`. Two fixes applied while porting:
    - Duplicate `id="attendance"` split — keep `#attendance` on
      "When are tickets available?"; rename the second ("What about if I
      can only attend for some of the time?") to `#part-time`
    - Formerly anchor-less complaint entry ("I have a problem with
      someone…") gets a new `#complaints` anchor
  - Final anchor list: `society-member`, `cant-bring`, `sponsor`,
    `accessibility`, `on-the-day`, `first-aid`, `complaints` (new),
    `contact`, `attendance`, `part-time` (renamed), `refunds`,
    `friend-tickets`, `vibe`, `rewards`, `gm-tickets`, `edit-submission`,
    `new-gm`, `what-can-i-run`, `killing-pcs`, `gms-to-bring`,
    `didnt-run`, `withdraw-game`, `preferences`, `friend-groups`,
    `players-to-bring`, plus a slug for the cosplay entry
    (currently anchor-less) — `cosplay`
  - Convert inline links to markdown `[text](url)` syntax
  - GM rewards list: use a markdown bullet list; tooltip entry keeps raw
    `<Tooltip>` / `<TooltipIcon>` / `<TooltipContent>` HTML inline
  - Preferences entry retains
    `{{ SETTINGS.DEFAULT_EVENT_SQID }}` interpolation inside a markdown
    link

### Phase 3: Generate and swap

- [x] **Run the script** to produce the new `faq.html.jinja`
- [x] **Spot-check the diff** — line count should drop dramatically; anchors
  and component calls should all be present
- [x] User eyeballs `/faq` in their VSCode-debugger dev session against the live site copy:
  - All 4 sections present, correct order
  - Expand each collapse, content matches
  - Click through an anchor link (e.g. `/faq#refunds`)
  - GM rewards tooltip still opens
  - Preferences link resolves to the default event's games page

### Phase 4: Tests

- [x] **Renderer unit tests** (`tests/scripts/test_build_faq.py`)
  - Fixture markdown → asserted-equal Jinja output for:
    - `## Section` → `<h2 class="text-xl">Section</h2>`
    - `### Q {#q}` + paragraph →
      `<Collapse ...>...<h3 id="q">Q</h3>...<p>...</p></CollapseContent></Collapse>`
    - Two consecutive `###` entries close/open cleanly
    - Bullet list gets the injected classes
    - `[text](https://example.com)` → `<L href="https://example.com">text</L>`
    - Inline `<Tooltip>...</Tooltip>` passes through
    - `{{ SETTINGS.X }}` survives verbatim (not HTML-escaped)
  - Idempotency test: run `build_faq.py --check` against current
    `faq.md` / `faq.html.jinja` pair and assert zero exit

#### Phase 4 verification

- [x] `pytest tests/scripts/test_build_faq.py`
- [x] `basedpyright`, `ruff check`

### Phase 5: Docs

- [x] **README note** — short "Editing the FAQ" subsection pointing at
  `faq.md` and the rebuild command
- [x] Confirm `CLAUDE.md` doesn't need updating (the conventions stay the
  same; this is page-specific)

## Acceptance Criteria

- [x] `basedpyright` passes
- [x] `ruff check` passes
- [x] `pytest` passes (including the new renderer tests)
- [x] `PYTHONPATH=. uv run python scripts/build_faq.py --check` exits 0 on
  a clean checkout
- [x] `/faq` in the dev server shows all 22 entries in 4 sections with
  visual parity to the current page
- [x] Anchor navigation (`/faq#<id>`) still jumps to the right entry for
  every previously-existing id
- [x] Golden D20 tooltip still opens from the GM rewards list
- [x] Preferences entry's link target contains the real default event
  sqid (interpolated, not literal `{{ ... }}`)
- [x] `faq.html.jinja` line count drops substantially (~490 → the shell +
  generated body; expected well under 300 lines, mostly machine-formatted)

## Risks and Mitigations

1. **Markdown parser escapes Jinja braces** — markdown-it may HTML-escape
   `{{` / `}}` in text tokens. Mitigation: emit `text` tokens verbatim
   (no `html.escape`) and verify with a unit test that Jinja interpolation
   round-trips. If escaping is unavoidable, add a protection pass that
   swaps `&#123;&#123;` back to `{{` post-render.
2. **`attrs_block` plugin behaviour on inline `{#id}`** — the plugin may
   target block-level attrs only. Mitigation: verify with a smoke test
   early in Phase 1; fall back to a small regex preprocessor that strips
   `{#id}` off heading lines and feeds it to the renderer out-of-band.
3. **Raw HTML handling in markdown-it** — by default markdown-it's
   `html: false` option escapes raw HTML. Mitigation: enable `html: True`
   on the parser so `<Tooltip>` passes through.
4. **Anchor duplication** — the current file has two entries with
   `id="attendance"`. Resolved in Phase 2: second instance renamed to
   `#part-time`; complaint + cosplay entries also gain fresh anchors.
   Any external links using the old duplicate id will continue to resolve
   to the first `#attendance` entry.
5. **Generated file drifts from source** — someone edits
   `faq.html.jinja` directly by mistake. Mitigation: prominent
   `{# GENERATED ... #}` banner; optional future follow-up to add
   `build_faq.py --check` to CI.

## Notes

- Follow-up candidates (not in scope here): extending the same pipeline
  to other copy-heavy static pages (e.g., home page sections), or
  running `build_faq.py --check` in CI.
- Keep the `<L>` component mapping for links consistent — it already
  handles external-vs-internal link styling, so we shouldn't regress by
  falling back to `<a>`.
