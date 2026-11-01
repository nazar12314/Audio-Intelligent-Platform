from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from audio_platform.api.dependencies import ContainerDep, CurrentUser
from audio_platform.modules.processing.schemas import ProcessingOut
from audio_platform.modules.processing.services import ProcessingQueries


def get_processing_queries(container: ContainerDep) -> ProcessingQueries:
    return container.processing_queries


Queries = Annotated[ProcessingQueries, Depends(get_processing_queries)]

processing_router = APIRouter(tags=["processing"])


@processing_router.get(
    "/recordings/{recording_id}/processing",
    response_model=ProcessingOut,
    summary="Processing status of a recording, with speech segments once VAD is done",
)
async def get_processing(
    recording_id: UUID, user: CurrentUser, queries: Queries
) -> ProcessingOut:
    return ProcessingOut.from_view(
        await queries.for_recording(user.user_id, recording_id)
    )
