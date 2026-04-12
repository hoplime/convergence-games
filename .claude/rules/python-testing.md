# Python Testing Conventions

## Framework

- pytest, run via `uv run pytest`.
- Run a single file: `uv run pytest path/to/test_file.py`
- Run a specific test: `uv run pytest -k "test_name"`

## Test Layout

- Tests live in a top-level `tests/` directory mirroring the `convergence_games/` source structure.
- Example: `tests/services/algorithm/test_game_allocator.py` tests `convergence_games/services/algorithm/game_allocator.py`.
- Test files are named `test_*.py`.
