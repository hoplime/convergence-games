import structlog
from litestar.logging.config import StructLoggingConfig

from convergence_games.logging.config import SHARED_PROCESSORS

# Mirror configure_logging()'s processor list. format_exc_info is intentionally
# excluded so ConsoleRenderer can format exceptions itself in dev; the JSON
# render path adds it back inside the ProcessorFormatter in prod.
logging_config = StructLoggingConfig(
    processors=[
        structlog.stdlib.filter_by_level,
        *SHARED_PROCESSORS,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=False,
    log_exceptions="always",
)
