import pytest

from audio_platform.modules.recordings.domain import UploadPolicy, UploadRejected

POLICY = UploadPolicy(
    max_size_bytes=100,
    part_size_bytes=10,
    allowed_content_types=frozenset({"audio/mpeg", "audio/wav"}),
)


def test_allowed_type_within_limit_passes() -> None:
    POLICY.check(content_type="audio/mpeg", size_bytes=100)


def test_unsupported_content_type_is_rejected() -> None:
    with pytest.raises(UploadRejected, match="video/mp4"):
        POLICY.check(content_type="video/mp4", size_bytes=1)


def test_file_over_the_limit_is_rejected() -> None:
    with pytest.raises(UploadRejected, match="100-byte limit"):
        POLICY.check(content_type="audio/wav", size_bytes=101)
