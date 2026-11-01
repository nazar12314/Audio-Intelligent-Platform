from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from audio_platform.api.dependencies import ContainerDep, CurrentUser
from audio_platform.modules.recordings.schemas import (
    MAX_PARTS,
    CompleteUploadIn,
    DownloadUrlOut,
    PartUploadUrlOut,
    RecordingOut,
    RecordingPageOut,
    RegisteredRecordingOut,
    RegisterRecordingIn,
    UploadPlanOut,
)
from audio_platform.modules.recordings.services import RecordingService


def get_recording_service(container: ContainerDep) -> RecordingService:
    return container.recording_service


Service = Annotated[RecordingService, Depends(get_recording_service)]
PartNumber = Annotated[int, Path(ge=1, le=MAX_PARTS)]

recordings_router = APIRouter(prefix="/recordings", tags=["recordings"])


@recordings_router.post(
    "",
    status_code=201,
    response_model=RegisteredRecordingOut,
    summary="Register a recording and start its multipart upload",
)
async def register_recording(
    body: RegisterRecordingIn, user: CurrentUser, service: Service
) -> RegisteredRecordingOut:
    registered = await service.register(
        user.user_id,
        filename=body.filename,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
    )
    recording, first_part = registered.recording, registered.first_part
    return RegisteredRecordingOut(
        recording=RecordingOut.from_domain(recording),
        upload=UploadPlanOut(
            part_size_bytes=recording.part_size_bytes,
            part_count=recording.part_count,
            url_ttl_s=service.url_ttl_s,
            first_part=PartUploadUrlOut(
                part_number=first_part.part_number,
                url=first_part.url,
                expires_at=first_part.expires_at,
            ),
        ),
    )


@recordings_router.post(
    "/{recording_id}/parts/{part_number}/upload-url",
    response_model=PartUploadUrlOut,
    summary="Presigned URL for uploading one part directly to storage",
)
async def create_part_upload_url(
    recording_id: UUID, part_number: PartNumber, user: CurrentUser, service: Service
) -> PartUploadUrlOut:
    part = await service.presign_part(user.user_id, recording_id, part_number)
    return PartUploadUrlOut(
        part_number=part.part_number, url=part.url, expires_at=part.expires_at
    )


@recordings_router.post(
    "/{recording_id}/complete",
    response_model=RecordingOut,
    summary="Complete the upload with the part ETags and verify the stored file",
)
async def complete_upload(
    recording_id: UUID, body: CompleteUploadIn, user: CurrentUser, service: Service
) -> RecordingOut:
    parts = [p.to_domain() for p in body.parts]
    return RecordingOut.from_domain(
        await service.complete(user.user_id, recording_id, parts)
    )


@recordings_router.post(
    "/{recording_id}/abort",
    response_model=RecordingOut,
    summary="Abort the upload",
)
async def abort_upload(
    recording_id: UUID, user: CurrentUser, service: Service
) -> RecordingOut:
    return RecordingOut.from_domain(await service.abort(user.user_id, recording_id))


@recordings_router.get(
    "", response_model=RecordingPageOut, summary="List your recordings, newest first"
)
async def list_recordings(
    user: CurrentUser,
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: UUID | None = None,
) -> RecordingPageOut:
    page = await service.list_recordings(user.user_id, limit=limit, cursor=cursor)
    return RecordingPageOut(
        items=[RecordingOut.from_domain(r) for r in page.items],
        next_cursor=page.next_cursor,
    )


@recordings_router.get(
    "/{recording_id}/download-url",
    response_model=DownloadUrlOut,
    summary="Presigned URL for downloading an uploaded recording",
)
async def create_download_url(
    recording_id: UUID, user: CurrentUser, service: Service
) -> DownloadUrlOut:
    download = await service.presign_download(user.user_id, recording_id)
    return DownloadUrlOut(url=download.url, expires_at=download.expires_at)


@recordings_router.get(
    "/{recording_id}", response_model=RecordingOut, summary="Get a recording"
)
async def get_recording(
    recording_id: UUID, user: CurrentUser, service: Service
) -> RecordingOut:
    return RecordingOut.from_domain(await service.get(user.user_id, recording_id))
