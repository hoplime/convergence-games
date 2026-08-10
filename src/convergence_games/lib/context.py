import contextvars

user_id_ctx: contextvars.ContextVar[int | None] = contextvars.ContextVar("user_id_ctx", default=None)
