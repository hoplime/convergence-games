from litestar.config.compression import CompressionConfig

compression_config = CompressionConfig(backend="brotli", exclude_opt_key="no_compression")
