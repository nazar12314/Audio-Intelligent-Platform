"""
S3 client lifecycle (AWS S3 in the cloud, RustFS locally).
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import aioboto3
from aiobotocore.config import AioConfig

from audio_platform.core.config import AwsSettings

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client


@asynccontextmanager
async def s3_client(settings: AwsSettings) -> AsyncIterator[S3Client]:
    """
    One client per process, reused for every call; closed on exit. Connects lazily.
    """
    config = AioConfig(
        connect_timeout=settings.connect_timeout_s,
        read_timeout=settings.read_timeout_s,
        retries={"mode": "standard", "max_attempts": settings.max_attempts},
        signature_version="s3v4",
        s3={"addressing_style": settings.s3_addressing_style},
    )
    session = aioboto3.Session(region_name=settings.region)
    async with session.client(
        "s3", endpoint_url=settings.endpoint_url, config=config
    ) as client:
        yield client


async def ping_bucket(client: S3Client, bucket: str) -> None:
    """
    Fails if the bucket is missing or the credentials cannot access it.
    """
    await client.head_bucket(Bucket=bucket)
