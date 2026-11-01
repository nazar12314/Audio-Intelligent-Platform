"""
Postgres and S3 adapters load with the API. The decoder and the VAD model need the
`processing` extra and are imported only by VAD workers.
"""

from audio_platform.modules.processing.adapters.postgres import (
    PostgresProcessingJobRepository,
    ProcessingJobRow,
    ProcessingStageRow,
    SqlProcessingUnitOfWork,
)
from audio_platform.modules.processing.adapters.s3_artifacts import S3ArtifactStorage

__all__ = [
    "PostgresProcessingJobRepository",
    "ProcessingJobRow",
    "ProcessingStageRow",
    "S3ArtifactStorage",
    "SqlProcessingUnitOfWork",
]
