
## Editing the FAQ

The FAQ page content lives in `convergence_games/app/templates/pages/faq.md`. The matching Jinja template is generated from it — do not edit `faq.html.jinja` by hand.

Markdown conventions:

- `##` opens a section heading
- `###` opens a collapsible question; it closes automatically at the next `##`/`###` or the end of the file
- Put `{#anchor}` on the line *above* a `###` to give it an id (used by `#…` links)
- Use standard markdown for paragraphs, bullet lists, `**bold**`, `*italic*`, `[text](url)` links
- Raw JinjaX components (`<Tooltip>`, `<L>`) and `{{ SETTINGS.* }}` interpolation work inline

After editing, regenerate the template:

```bash
PYTHONPATH=. uv run python scripts/build_faq.py
```

Use `--check` to verify the committed `faq.html.jinja` is up to date with `faq.md`.
