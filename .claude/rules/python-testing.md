---
alwaysApply: false
paths: **/*.py
---

# Python Testing Conventions

## Framework

- pytest, run via `pytest`.
- Run a single file: `pytest path/to/test_file.py`
- Run a specific test: `pytest -k "test_name"`

## Test Layout

- Tests live in a top-level `tests/` directory mirroring the `src/convergence_games/` source structure.
- Example: `tests/lib/test_auth.py` tests `src/convergence_games/lib/auth.py`.
- Test files are named `test_*.py`.
