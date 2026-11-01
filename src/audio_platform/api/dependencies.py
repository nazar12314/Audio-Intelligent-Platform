from typing import Annotated, cast

from fastapi import Depends, Request

from audio_platform.core.auth import Principal
from audio_platform.core.container import Container


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]


async def get_current_user(request: Request, container: ContainerDep) -> Principal:
    return await container.authenticator.authenticate(request.headers)


CurrentUser = Annotated[Principal, Depends(get_current_user)]
