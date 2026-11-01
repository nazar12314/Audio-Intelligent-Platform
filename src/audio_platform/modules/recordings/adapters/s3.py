from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING

from botocore.exceptions import BotoCoreError, ClientError

from audio_platform.core.exceptions import DependencyUnavailable
from audio_platform.modules.recordings.domain import StoredObject, UploadedPart
from audio_platform.modules.recordings.ports import PartsRejected, UploadNotFound

if TYPE_CHECKING:
    from types_aiobotocore_s3 import S3Client

_PARTS_REJECTED = {"InvalidPart", "InvalidPartOrder", "EntityTooSmall"}
_NOT_FOUND = {"404", "NoSuchKey", "NotFound"}


def _code(exc: ClientError) -> str:
    return str(exc.response.get("Error", {}).get("Code", ""))


@contextmanager
def _translate_errors() -> Iterator[None]:
    try:
        yield
    except ClientError as exc:
        code = _code(exc)
        if code == "NoSuchUpload":
            raise UploadNotFound from None
        if code in _PARTS_REJECTED:
            raise PartsRejected(f"storage rejected the parts: {code}") from None
        raise DependencyUnavailable("object storage unavailable") from None
    except BotoCoreError:
        raise DependencyUnavailable("object storage unavailable") from None


class S3AudioObjectStorage:
    def __init__(self, client: S3Client, presigner: S3Client, bucket: str) -> None:
        self._client = client
        self._presigner = presigner
        self._bucket = bucket

    async def create_multipart_upload(self, key: str, content_type: str) -> str:
        with _translate_errors():
            response = await self._client.create_multipart_upload(
                Bucket=self._bucket, Key=key, ContentType=content_type
            )
        return response["UploadId"]

    async def presign_upload_part(
        self,
        key: str,
        upload_id: str,
        part_number: int,
        expires_in_s: int,
        *,
        content_length: int,
    ) -> str:
        with _translate_errors():
            return await self._presigner.generate_presigned_url(
                "upload_part",
                Params={
                    "Bucket": self._bucket,
                    "Key": key,
                    "UploadId": upload_id,
                    "PartNumber": part_number,
                    "ContentLength": content_length,
                },
                ExpiresIn=expires_in_s,
            )

    async def presign_download(self, key: str, expires_in_s: int) -> str:
        with _translate_errors():
            return await self._presigner.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expires_in_s,
            )

    async def complete_multipart_upload(
        self, key: str, upload_id: str, parts: Sequence[UploadedPart]
    ) -> None:
        with _translate_errors():
            await self._client.complete_multipart_upload(
                Bucket=self._bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={
                    "Parts": [
                        {"PartNumber": p.part_number, "ETag": p.etag} for p in parts
                    ]
                },
            )

    async def abort_multipart_upload(self, key: str, upload_id: str) -> None:
        with _translate_errors():
            await self._client.abort_multipart_upload(
                Bucket=self._bucket, Key=key, UploadId=upload_id
            )

    async def head_object(self, key: str) -> StoredObject | None:
        try:
            response = await self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if _code(exc) in _NOT_FOUND:
                return None
            with _translate_errors():
                raise
        except BotoCoreError:
            raise DependencyUnavailable("object storage unavailable") from None
        return StoredObject(
            size_bytes=response["ContentLength"],
            content_type=response.get("ContentType"),
            etag=response["ETag"],
            version_id=response.get("VersionId"),
        )

    async def delete_object(self, key: str, *, version_id: str | None = None) -> None:
        with _translate_errors():
            if version_id:
                await self._client.delete_object(
                    Bucket=self._bucket, Key=key, VersionId=version_id
                )
            else:
                await self._client.delete_object(Bucket=self._bucket, Key=key)
