"""Top-level pytest fixtures and test-environment setup.

Sets minimal environment variables before any ``convergence_games`` import
happens (the package's ``__init__`` eagerly constructs the app and its
settings, which require these to be present).
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet

os.environ.setdefault("IMAGE_STORAGE_MODE", "filesystem")
os.environ.setdefault("IMAGE_STORAGE_PATH", str(Path("/tmp") / "convergence-games-tests"))
os.environ.setdefault("SIGNING_KEY", Fernet.generate_key().decode())
os.environ.setdefault("TOKEN_SECRET", "test-token-secret")
os.environ.setdefault("SENTRY_ENABLE", "false")
