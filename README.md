# Convergence Games

Web application for managing tabletop RPG convention events, built for the [Waikato Role-Playing Guild](https://waikatorpg.co.nz)'s "Convergence" event.

Live at: https://convergence.waikatorpg.co.nz

## What it does

- **Game submissions** — GMs submit games with descriptions, player counts, content warnings, genres, and scheduling/equipment requirements
- **Event management** — organisers review submissions, configure rooms/tables/time slots, and manage the schedule
- **Player preferences** — players rate games using a dice-based preference system (D4–D20, higher = stronger preference)
- **Party system** — players can form parties to be allocated together
- **Automatic allocation** — an algorithm assigns players to sessions based on preferences, party membership, and constraints
- **Check-in and D20 economy** — day-of-event check-in tracking and a virtual currency system for preference boosts

## Tech stack

- **Backend**: Python 3.13, [Litestar](https://litestar.dev/), SQLAlchemy (async), PostgreSQL
- **Frontend**: Server-rendered [JinjaX](https://jinjax.scaletti.dev/) templates, [HTMX](https://htmx.org/), [TailwindCSS v4](https://tailwindcss.com/) + [DaisyUI v5](https://daisyui.com/)
- **Client-side**: TypeScript bundled via Vite (TipTap rich text editor, SortableJS drag-and-drop)
- **Package management**: [uv](https://docs.astral.sh/uv/) (Python), npm (Node)
- **Database migrations**: Alembic via [Advanced Alchemy](https://docs.advanced-alchemy.litestar.dev/)

## Licensing

This repository is licensed under the MIT License. The following assets are **not** covered by this license:

### Waikato Role-Playing Guild

Copyright the Waikato Role-Playing Guild. All rights reserved.

- `convergence_games/app/static/favicon/` — favicon assets
- Embedded Convergence logo SVG in `convergence_games/app/templates/components/NavBar.html.jinja`

### Third-party brand assets

Owned by their respective owners. All rights reserved.

- `convergence_games/app/static/icons/logos/` — authentication provider logos (Discord, Google)
- `convergence_games/app/static/images/sponsors/` — sponsor logos

### Vendored JavaScript libraries

Distributed under their own open-source licenses.

- `htmx.js` / `htmx.min.js` — [htmx](https://htmx.org/) (BSD 2-Clause)
- `_hyperscript.min.js` — [hyperscript](https://hyperscript.org/) (BSD 2-Clause)
- `qrcode.min.js` — QR code generator
- `preload.js` — htmx preload extension
- `path-params.js` — htmx path-params extension
