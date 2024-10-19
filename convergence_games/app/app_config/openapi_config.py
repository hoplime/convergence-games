from litestar.openapi.config import OpenAPIConfig
from litestar.openapi.plugins import SwaggerRenderPlugin

openapi_config = OpenAPIConfig(
    title="Convergence Games",
    version="0.1.0",
    path="/docs",
    render_plugins=[SwaggerRenderPlugin()],
)
