# Convergence Games Website

## Requirements

- Windows or Linux.
- `poetry` for dependency installation - https://python-poetry.org/docs/ with Python 3.12
  - Install as appropriate for your system.
- Soon this will use Docker instead, and the usage instructions will change :P

## Usage

```bash
poetry install
uvicorn --reload --host 0.0.0.0 convergence_games.app:app
```

And visit `https://localhost:8000`.
