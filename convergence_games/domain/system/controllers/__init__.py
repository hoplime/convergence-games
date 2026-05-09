from ._favicon import favicon_router
from ._health import health_check
from ._static import static_files_router

__all__ = ["favicon_router", "health_check", "static_files_router"]
