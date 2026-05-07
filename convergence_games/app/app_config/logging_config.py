import structlog
from litestar.logging.config import StructLoggingConfig

from convergence_games.logging.config import SHARED_PROCESSORS

logging_config = StructLoggingConfig(
    processors=[
        structlog.stdlib.filter_by_level,
        *SHARED_PROCESSORS,
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
    log_exceptions="always",
)
