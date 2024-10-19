from pathlib import Path

from litestar.static_files import create_static_files_router

static_files_router = create_static_files_router(path="/static", directories=[Path(__file__).parent.parent / "static"])
