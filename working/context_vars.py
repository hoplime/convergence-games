import asyncio
from collections.abc import AsyncIterator
from contextvars import ContextVar

from litestar import Litestar, get
from litestar.testing import AsyncTestClient

VAR = ContextVar[int]("VAR", default=0)
EXPECTED_VALUE = 100


async def provide_extra() -> AsyncIterator[int]:
    yield EXPECTED_VALUE


async def set_var(extra: int) -> AsyncIterator[int]:
    token = VAR.set(extra)
    try:
        yield extra
    finally:
        pass
    #     VAR.reset(token)


@get("/example")
async def example(set_var: int) -> int:
    print(set_var)
    return VAR.get()


app = Litestar([example], debug=True, dependencies={"extra": provide_extra, "set_var": set_var})


async def test() -> None:
    async with AsyncTestClient(app) as client:
        response = await client.get("/example")
        assert (value := response.json()) == EXPECTED_VALUE, f"Expected {EXPECTED_VALUE}, got {value}"


if __name__ == "__main__":
    asyncio.run(test())
