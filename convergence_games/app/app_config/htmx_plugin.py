from litestar.plugins.htmx import HTMXConfig, HTMXPlugin

htmx_config = HTMXConfig(set_request_class_globally=True)
htmx_plugin = HTMXPlugin(htmx_config)
