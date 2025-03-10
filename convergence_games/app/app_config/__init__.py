from .compression_config import compression_config
from .htmx_plugin import htmx_plugin
from .jwt_cookie_auth import jwt_cookie_auth
from .openapi_config import openapi_config
from .sqlalchemy_plugin import sqlalchemy_plugin
from .template_config import template_config

__all__ = [
    "compression_config",
    "htmx_plugin",
    "openapi_config",
    "sqlalchemy_plugin",
    "template_config",
    "jwt_cookie_auth",
]
