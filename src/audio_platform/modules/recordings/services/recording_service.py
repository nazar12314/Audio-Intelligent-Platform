import contextlib
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from audio_platform.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationFailed,
)
from audio_platform.core.logging import LogEvent, get_logger
from audio_platform.core.messaging import Destinations, Event
from audio_platform.modules.recordings.domain import (
    InvalidPartList,
    Recording,
    RecordingStatus,
    StoredObject,
    UploadedPart,
    UploadPolicy,
    UploadRejected,
)
from audio_platform.modules.recordings.ports import (
    AudioObjectStorage,
    PartsRejected,
    RecordingUnitOfWork,
    UnitOfWorkFactory,
    UploadNotFound,
)

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]

logger = get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _uploaded_event(recording: Recording) -> Event:
    return Event.new(
        "recordings.recording.uploaded",
        {
            "recording_id": str(recording.id),
            "owner_id": str(recording.owner_id),
            "object_key": recording.object_key,
            "content_type": recording.content_type,
            "size_bytes": recording.size_bytes,
        },
    )


@dataclass(frozen=True, slots=True)
class PresignedPart:
    part_number: int
    url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RegisteredRecording:
    recording: Recording
    first_part: PresignedPart


@dataclass(frozen=True, slots=True)
class PresignedDownload:
    url: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class RecordingPage:
    items: list[Recording]
    next_cursor: UUID | None


class RecordingService:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        storage: AudioObjectStorage,
        policy: UploadPolicy,
        *,
        url_ttl_s: int,
        clock: Clock = _utcnow,
        new_id: IdFactory = uuid.uuid7,
    ) -> None:
        self._uow = uow
        self._storage = storage
        self._policy = policy
        self._url_ttl_s = url_ttl_s
        self._clock = clock
        self._new_id = new_id

    @property
    def url_ttl_s(self) -> int:
        return self._url_ttl_s

    async def register(
        self, owner_id: UUID, *, filename: str, content_type: str, size_bytes: int
    ) -> RegisteredRecording:
        try:
            self._policy.check(content_type=content_type, size_bytes=size_bytes)
        except UploadRejected as exc:
            raise ValidationFailed(str(exc)) from None

        now = self._clock()
        recording = Recording.register(
            recording_id=self._new_id(),
            owner_id=owner_id,
            filename=filename,
            content_type=content_type,
            size_bytes=size_bytes,
            part_size_bytes=self._policy.part_size_bytes,
            now=now,
        )
        upload_id = await self._storage.create_multipart_upload(
            recording.object_key, content_type
        )
        recording.attach_upload(upload_id, now=now)
        try:
            async with self._uow() as uow:
                await uow.recordings.add(recording)
                await uow.commit()
        except BaseException:
            await self._abort_quietly(recording.object_key, upload_id)
            raise

        logger.info(
            LogEvent.RECORDING_REGISTERED,
            recording_id=str(recording.id),
            size_bytes=size_bytes,
            part_count=recording.part_count,
        )
        # Saves small, single-part files a round trip before their only upload.
        first_part = await self._presign(recording, upload_id, 1)
        return RegisteredRecording(recording=recording, first_part=first_part)

    async def get(self, owner_id: UUID, recording_id: UUID) -> Recording:
        async with self._uow() as uow:
            return await self._load(uow, owner_id, recording_id)

    async def list_recordings(
        self, owner_id: UUID, *, limit: int, cursor: UUID | None = None
    ) -> RecordingPage:
        async with self._uow() as uow:
            items = await uow.recordings.list_for_owner(
                owner_id, limit=limit + 1, before_id=cursor
            )
        has_more = len(items) > limit
        items = items[:limit]
        return RecordingPage(items, items[-1].id if has_more else None)

    async def presign_download(
        self, owner_id: UUID, recording_id: UUID
    ) -> PresignedDownload:
        recording = await self.get(owner_id, recording_id)
        if recording.status is not RecordingStatus.UPLOADED:
            raise ConflictError(f"recording is {recording.status}, not uploaded")
        url = await self._storage.presign_download(
            recording.object_key, self._url_ttl_s
        )
        expires_at = self._clock() + timedelta(seconds=self._url_ttl_s)
        return PresignedDownload(url=url, expires_at=expires_at)

    async def presign_part(
        self, owner_id: UUID, recording_id: UUID, part_number: int
    ) -> PresignedPart:
        recording = await self.get(owner_id, recording_id)
        upload_id = self._require_pending_upload(recording)
        return await self._presign(recording, upload_id, part_number)

    async def _presign(
        self, recording: Recording, upload_id: str, part_number: int
    ) -> PresignedPart:
        try:
            content_length = recording.part_size_for(part_number)
        except InvalidPartList as exc:
            raise ValidationFailed(str(exc)) from None

        url = await self._storage.presign_upload_part(
            recording.object_key,
            upload_id,
            part_number,
            self._url_ttl_s,
            content_length=content_length,
        )
        expires_at = self._clock() + timedelta(seconds=self._url_ttl_s)
        return PresignedPart(part_number=part_number, url=url, expires_at=expires_at)

    async def complete(
        self, owner_id: UUID, recording_id: UUID, parts: Sequence[UploadedPart]
    ) -> Recording:
        recording = await self.get(owner_id, recording_id)
        if recording.status is RecordingStatus.UPLOADED:
            return recording  # a retried completion is not an error
        upload_id = self._require_pending_upload(recording)
        try:
            recording.check_completed_parts(parts)
        except InvalidPartList as exc:
            raise ValidationFailed(str(exc)) from None

        # Storage calls run outside any transaction: holding a pooled connection and a
        # row lock through slow S3 calls would starve the pool under parallel uploads.
        stored = await self._complete_in_storage(recording, upload_id, parts)

        uploaded = False
        async with self._uow() as uow:
            recording = await self._load(uow, owner_id, recording_id, for_update=True)
            if recording.status is RecordingStatus.UPLOADED:
                return recording  # a concurrent completion won
            still_pending = recording.status is RecordingStatus.PENDING_UPLOAD
            if still_pending:
                uploaded = self._verify(recording, stored)
                await uow.recordings.update(recording)
                if uploaded:
                    await uow.outbox.add(
                        _uploaded_event(recording),
                        destination=Destinations.PIPELINE_EVENTS,
                    )
                await uow.commit()

        if not still_pending:
            # Aborted meanwhile: whatever storage assembled now belongs to nothing.
            await self._discard(recording, stored)
            raise ConflictError(f"recording is {recording.status}, not pending upload")
        if uploaded:
            logger.info(LogEvent.RECORDING_UPLOADED, recording_id=str(recording.id))
        else:
            await self._discard(recording, stored)
            logger.warning(
                LogEvent.RECORDING_UPLOAD_FAILED,
                recording_id=str(recording.id),
                reason=recording.failure_reason,
            )
        return recording

    async def abort(self, owner_id: UUID, recording_id: UUID) -> Recording:
        recording = await self.get(owner_id, recording_id)
        if recording.status is RecordingStatus.ABORTED:
            return recording
        upload_id = self._require_pending_upload(recording)
        try:
            await self._storage.abort_multipart_upload(recording.object_key, upload_id)
            completed_in_storage = False
        except UploadNotFound:
            # Expired, or completed in storage without being recorded.
            completed_in_storage = True

        async with self._uow() as uow:
            recording = await self._load(uow, owner_id, recording_id, for_update=True)
            if recording.status is RecordingStatus.ABORTED:
                return recording
            self._require_pending_upload(recording)  # a concurrent completion won
            recording.mark_aborted(now=self._clock())
            await uow.recordings.update(recording)
            await uow.commit()

        if completed_in_storage:
            await self._discard_existing(recording)
        logger.info(LogEvent.RECORDING_ABORTED, recording_id=str(recording.id))
        return recording

    async def _complete_in_storage(
        self, recording: Recording, upload_id: str, parts: Sequence[UploadedPart]
    ) -> StoredObject | None:
        ordered = sorted(parts, key=lambda p: p.part_number)
        try:
            await self._storage.complete_multipart_upload(
                recording.object_key, upload_id, ordered
            )
        except PartsRejected as exc:
            raise ValidationFailed(str(exc)) from None
        except UploadNotFound:
            # Either it expired, or an earlier completion succeeded in storage but
            # was never recorded: the HEAD below tells the two apart.
            pass
        return await self._storage.head_object(recording.object_key)

    def _verify(self, recording: Recording, stored: StoredObject | None) -> bool:
        now = self._clock()
        if stored is None:
            recording.mark_failed("upload expired or was aborted", now=now)
            return False
        if stored.size_bytes != recording.size_bytes:
            recording.mark_failed(
                f"size mismatch: declared {recording.size_bytes} bytes, "
                f"stored {stored.size_bytes}",
                now=now,
            )
            return False
        recording.mark_uploaded(etag=stored.etag, now=now)
        return True

    @staticmethod
    async def _load(
        uow: RecordingUnitOfWork,
        owner_id: UUID,
        recording_id: UUID,
        *,
        for_update: bool = False,
    ) -> Recording:
        recording = await uow.recordings.get_for_owner(
            recording_id, owner_id, for_update=for_update
        )
        if recording is None:
            raise NotFoundError("recording", recording_id)
        return recording

    @staticmethod
    def _require_pending_upload(recording: Recording) -> str:
        if (
            recording.status is not RecordingStatus.PENDING_UPLOAD
            or recording.upload_id is None
        ):
            raise ConflictError(f"recording is {recording.status}, not pending upload")
        return recording.upload_id

    async def _discard(self, recording: Recording, stored: StoredObject | None) -> None:
        """
        Delete an object no recording points to. Only called after the recording's
        final status is committed, so a concurrent request cannot still rely on it.
        """
        if stored is None:
            return
        try:
            await self._storage.delete_object(
                recording.object_key, version_id=stored.version_id
            )
        except Exception:
            logger.warning(
                LogEvent.RECORDING_OBJECT_CLEANUP_FAILED,
                recording_id=str(recording.id),
                exc_info=True,
            )

    async def _discard_existing(self, recording: Recording) -> None:
        try:
            stored = await self._storage.head_object(recording.object_key)
        except Exception:
            logger.warning(
                LogEvent.RECORDING_OBJECT_CLEANUP_FAILED,
                recording_id=str(recording.id),
                exc_info=True,
            )
            return
        await self._discard(recording, stored)

    async def _abort_quietly(self, key: str, upload_id: str) -> None:
        # Best effort: the bucket lifecycle rule aborts leftovers after 7 days.
        with contextlib.suppress(Exception):
            await self._storage.abort_multipart_upload(key, upload_id)
