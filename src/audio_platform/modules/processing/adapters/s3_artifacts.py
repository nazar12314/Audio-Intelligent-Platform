import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

from botocore.exceptions import BotoCoreError, ClientError

from audio_platform.core.exceptions import DependencyUnavailable

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except ClientError, BotoCoreError:
        raise DependencyUnavailable("object storage unavailable") from None


class S3ArtifactStorage:
    """
    Files stream through disk: recordings can be gigabytes.
    """

    def __init__(self, client: S3Client, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    async def download(self, key: str, path: Path) -> None:
        with _translate_errors():
            response = await self._client.get_object(Bucket=self._bucket, Key=key)
            with path.open("wb") as file:
                async for chunk in response["Body"].iter_chunks(1024 * 1024):
                    file.write(chunk)

    async def upload_file(self, key: str, path: Path, *, content_type: str) -> None:
        with _translate_errors(), path.open("rb") as file:
            await self._client.upload_fileobj(
                file, self._bucket, key, ExtraArgs={"ContentType": content_type}
            )

    async def put_json(self, key: str, payload: Any) -> None:
        with _translate_errors():
            await self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(payload).encode(),
                ContentType="application/json",
            )

    async def get_json(self, key: str) -> Any | None:
        try:
            response = await self._client.get_object(Bucket=self._bucket, Key=key)
            body = await response["Body"].read()
        except ClientError as exc:
            if str(exc.response.get("Error", {}).get("Code", "")) in _NOT_FOUND:
                return None
            raise DependencyUnavailable("object storage unavailable") from None
        except BotoCoreError:
            raise DependencyUnavailable("object storage unavailable") from None
        return json.loads(body)
