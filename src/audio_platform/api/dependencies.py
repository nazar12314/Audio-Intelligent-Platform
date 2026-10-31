"""Small dependency functions: the API's only way to reach the container. Override them in tests."""

from typing import Annotated, cast

from fastapi import Depends, Request

from audio_platform.core.container import Container


def get_container(request: Request) -> Container:
    return cast(Container, request.app.state.container)


ContainerDep = Annotated[Container, Depends(get_container)]
