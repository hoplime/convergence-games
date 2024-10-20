from typing import TYPE_CHECKING

from litestar.response import Template as Template

if TYPE_CHECKING:
    from typing import Any, Dict, Optional

    from jinja2_fragments.litestar import HTMXBlockTemplate as _HTMXBlockTemplate
    from litestar.background_tasks import BackgroundTask, BackgroundTasks
    from litestar.contrib.htmx.types import EventAfterType, PushUrlType, ReSwapMethod
    from litestar.enums import MediaType
    from litestar.status_codes import HTTP_200_OK
    from litestar.types import ResponseCookies

    class HTMXBlockTemplate(_HTMXBlockTemplate):
        def __init__(
            self,
            push_url: Optional[PushUrlType] = None,
            re_swap: Optional[ReSwapMethod] = None,
            re_target: Optional[str] = None,
            trigger_event: Optional[str] = None,
            params: Optional[Dict[str, Any]] = None,
            after: Optional[EventAfterType] = None,
            block_name: Optional[str] = None,
            *,
            template_name: str | None = None,
            template_str: str | None = None,
            background: BackgroundTask | BackgroundTasks | None = None,
            context: dict[str, Any] | None = None,
            cookies: ResponseCookies | None = None,
            encoding: str = "utf-8",
            headers: dict[str, Any] | None = None,
            media_type: MediaType | str | None = None,
            status_code: int = HTTP_200_OK,
        ): ...
else:
    from jinja2_fragments.litestar import HTMXBlockTemplate  # noqa: F401
