"""S3-compatible object storage client."""

from audio_platform.infrastructure.storage.s3 import ping_bucket, s3_client

__all__ = ["ping_bucket", "s3_client"]
