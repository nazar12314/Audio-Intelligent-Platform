import copy
import json
import uuid
import wave
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, Self

from audio_platform.core.exceptions import DependencyUnavailable
from audio_platform.core.messaging import Event
from audio_platform.modules.processing.domain import (
    AudioInfo,
    InvalidAudio,
    ProcessingJob,
)
from tests.fakes.recordings import InMemoryOutbox


class InMemoryJobRepository:
    def __init__(self, rows: dict[uuid.UUID, ProcessingJob]) -> None:
        self._rows = rows

    async def add(self, job: ProcessingJob) -> None:
        self._rows[job.id] = copy.deepcopy(job)

    async def get(
        self, job_id: uuid.UUID, *, for_update: bool = False
    ) -> ProcessingJob | None:
        return copy.deepcopy(self._rows.get(job_id))

    async def find_by_recording(self, recording_id: uuid.UUID) -> ProcessingJob | None:
        return next(
            (
                copy.deepcopy(j)
                for j in self._rows.values()
                if j.recording_id == recording_id
            ),
            None,
        )

    async def get_for_owner(
        self, recording_id: uuid.UUID, owner_id: uuid.UUID
    ) -> ProcessingJob | None:
        job = await self.find_by_recording(recording_id)
        return job if job is not None and job.owner_id == owner_id else None

    async def update(self, job: ProcessingJob) -> None:
        if job.id in self._rows:
            self._rows[job.id] = copy.deepcopy(job)


class InMemoryProcessingStore:
    def __init__(self) -> None:
        self.jobs: dict[uuid.UUID, ProcessingJob] = {}
        self.outbox: list[tuple[str, Event]] = []
        self.open_transactions = 0

    def unit_of_work(self) -> InMemoryProcessingUnitOfWork:
        return InMemoryProcessingUnitOfWork(self)

    def events(self, type: str) -> list[Event]:
        return [event for _, event in self.outbox if event.type == type]


class InMemoryProcessingUnitOfWork:
    def __init__(self, store: InMemoryProcessingStore) -> None:
        self._store = store

    @property
    def jobs(self) -> InMemoryJobRepository:
        return self._jobs

    @property
    def outbox(self) -> InMemoryOutbox:
        return InMemoryOutbox(self._pending)

    async def __aenter__(self) -> Self:
        self._store.open_transactions += 1
        self._working = copy.deepcopy(self._store.jobs)
        self._pending: list[tuple[str, Event]] = []
        self._jobs = InMemoryJobRepository(self._working)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._store.open_transactions -= 1

    async def commit(self) -> None:
        self._store.jobs = copy.deepcopy(self._working)
        self._store.outbox.extend(self._pending)


class InMemoryArtifactStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail_downloads: int = 0  # the next N downloads raise
        self.before_call: Callable[[], None] = lambda: None

    async def download(self, key: str, path: Path) -> None:
        self.before_call()
        if self.fail_downloads:
            self.fail_downloads -= 1
            raise DependencyUnavailable("object storage unavailable")
        path.write_bytes(self.objects[key])

    async def upload_file(self, key: str, path: Path, *, content_type: str) -> None:
        self.before_call()
        self.objects[key] = path.read_bytes()

    async def put_json(self, key: str, payload: Any) -> None:
        self.before_call()
        self.objects[key] = json.dumps(payload).encode()

    async def get_json(self, key: str) -> Any | None:
        body = self.objects.get(key)
        return None if body is None else json.loads(body)


class FakeDecoder:
    """Pretends every input is `seconds` of audio; `invalid` makes it unreadable."""

    def __init__(self, seconds: float = 2.0) -> None:
        self.seconds = seconds
        self.invalid: str | None = None

    def probe(self, path: Path) -> AudioInfo:
        if self.invalid:
            raise InvalidAudio(self.invalid)
        return AudioInfo("wav", "pcm_s16le", 44_100, 2, self.seconds)

    def normalize(
        self, source: Path, target: Path, *, sample_rate: int, max_samples: int
    ) -> int:
        samples = int(self.seconds * sample_rate)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"\x00\x00" * samples)
        return samples


class FakeSpeechModel:
    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = probabilities

    def probabilities(self, wav_path: Path) -> list[float]:
        return list(self._probabilities)
