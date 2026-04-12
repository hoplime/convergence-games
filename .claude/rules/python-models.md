# Python Models & Database Conventions

## SQLAlchemy Models

- All models in `convergence_games/db/models.py`, inheriting from `Base` (which extends `BigIntAuditBase` + `UserAuditColumns`).
- Use SQLAlchemy 2.0+ `Mapped[T]` annotations for all columns.
- All relationships default to `lazy="noload"` to prevent N+1 queries. Relationships must be explicitly loaded in queries via `selectinload()`, `joinedload()`, etc.
- Cross-event foreign key constraints use the `foreign_key_constraint_with_event()` helper to ensure referential integrity within an event.
- Use `@sqla_event.listens_for(Model, "before_insert")` for auto-populating redundant foreign keys (e.g., `event_id`).

## Enums

- String enums: `enum.StrEnum` with human-readable values (e.g., `LIGHT = "Light"`).
- Bit flag enums: extend `FlagWithNotes` (`enum.IntFlag` subclass) with `__notes__`, `__form_notes__`, `__tooltips__`, `__icons__` class-var dicts.
- Requirement/Facility enums: extend `Requirement` or `Facility` (subclasses of `FlagWithNotes`) for game/room/table matching logic.
- Add `@property` methods on enums for computed display values.

## Pydantic Models

- Use `BaseModel` for request/response validation (form data, query params).
- Use `ConfigDict(arbitrary_types_allowed=True)` when fields include non-standard types like `UploadFile`.
- Use `@model_validator(mode="after")` for cross-field validation (see `Settings` class).
- Use `@dataclass` (stdlib) for simple internal data containers that don't need validation.

## Sqid Encoding

- Database IDs are obfuscated in URLs using Sqids (`convergence_games/db/ocean.py`).
- `swim(obj)` encodes, `sink(sqid)` decodes. `swim_upper`/`sink_upper` for uppercase sqids.
- IDs are salted per model class name via `_ink()`.
- Use `Annotated[int, BeforeValidator(sink)]` for automatic decoding in route parameters.

## Migrations

- Managed via Alembic through Advanced Alchemy's Litestar integration.
- Generate: `uv run litestar --app convergence_games.app:app database make-migrations -m "description"`
- Apply: `uv run litestar --app convergence_games.app:app database upgrade`
- Files in `convergence_games/migrations/versions/`, auto-formatted by ruff post-write hook.
