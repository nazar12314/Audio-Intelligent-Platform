"""Presigning is local (no network): these guard the host clients will upload to."""

from urllib.parse import urlsplit

import pytest

from audio_platform.core.config import AwsSettings
from audio_platform.infrastructure.storage import s3_client

BUCKET = "audio-platform-dev-recordings-123456789012"


@pytest.fixture(autouse=True)
def _fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test-" + "x" * 32)
    monkeypatch.delenv("AWS_PROFILE", raising=False)


async def _presigned_host(settings: AwsSettings) -> str:
    async with s3_client(settings) as s3:
        url = await s3.generate_presigned_url(
            "upload_part", Params={"Bucket": BUCKET, "Key": "users/u/k", "UploadId": "u1", "PartNumber": 1}
        )
    return urlsplit(url).netloc


async def test_default_settings_presign_for_the_regional_virtual_host() -> None:
    assert await _presigned_host(AwsSettings(region="eu-central-1")) == f"{BUCKET}.s3.eu-central-1.amazonaws.com"


async def test_local_endpoint_with_path_style_presigns_for_that_endpoint() -> None:
    settings = AwsSettings(region="us-east-1", endpoint_url="http://localhost:9000", s3_addressing_style="path")
    assert await _presigned_host(settings) == "localhost:9000"
