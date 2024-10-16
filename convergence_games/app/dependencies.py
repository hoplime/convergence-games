from typing import Annotated

from fastapi import Depends, Request


async def get_hx_target(request: Request) -> str | None:
    print("HX-Target:", request.headers.get("hx-target"))
    return request.headers.get("hx-target")


HxTarget = Annotated[str | None, Depends(get_hx_target)]
