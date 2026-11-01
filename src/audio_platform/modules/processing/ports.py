"""Interfaces the processing pipeline depends on."""

from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from audio_platform.core.messaging import Outbox
from audio_platform.modules.processing.domain import (
    AudioAnalysis,
    AudioInfo,
    ProcessingJob,
)


class ProcessingJobRepository(Protocol):
    async def add(self, job: ProcessingJob) -> None: ...

    async def get(
        self, job_id: UUID, *, for_update: bool = False
    ) -> ProcessingJob | None: ...

    async def find_by_recording(self, recording_id: UUID) -> ProcessingJob | None: ...

    async def get_for_owner(
        self, recording_id: UUID, owner_id: UUID
    ) -> ProcessingJob | None: ...

    async def update(self, job: ProcessingJob) -> None: ...


class ProcessingUnitOfWork(Protocol):
    @property
    def jobs(self) -> ProcessingJobRepository: ...

    @property
    def outbox(self) -> Outbox: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


ProcessingUnitOfWorkFactory = Callable[[], ProcessingUnitOfWork]


class ArtifactStorage(Protocol):
    async def download(self, key: str, path: Path) -> None: ...

    async def upload_file(self, key: str, path: Path, *, content_type: str) -> None: ...

    async def put_json(self, key: str, payload: Any) -> None: ...

    async def get_json(self, key: str) -> Any | None: ...


class AudioDecoder(Protocol):
    """CPU-bound and blocking: callers run it in a worker thread."""

    def probe(self, path: Path) -> AudioInfo:
        """Raise InvalidAudio when the file has no decodable audio stream."""
        ...

    def normalize(
        self, source: Path, target: Path, *, sample_rate: int, max_samples: int
    ) -> int:
        """
        Decode to mono 16-bit PCM WAV at `sample_rate`; return the sample count.
        Raise InvalidAudio on decode errors or past `max_samples`.
        """
        ...


class SpeechProbabilityModel(Protocol):
    """CPU-bound and blocking: callers run it in a worker thread."""

    def probabilities(self, wav_path: Path) -> list[float]:
        """Speech probability per 512-sample window of a 16 kHz mono WAV."""
        ...


class AnalysisTimedOut(Exception):
    """The analysis exceeded its time limit and was stopped."""


class AudioAnalyzer(Protocol):
    async def analyze(
        self, source: Path, target: Path, *, max_duration_s: int
    ) -> AudioAnalysis:
        """
        Validate `source`, normalize it into `target` (16 kHz mono WAV) and score
        speech. Raise InvalidAudio for unusable files and AnalysisTimedOut when the
        time limit is exceeded.
        """
        ...
