from dataclasses import dataclass


class UploadRejected(Exception):
    pass


@dataclass(frozen=True, slots=True)
class UploadPolicy:
    max_size_bytes: int
    part_size_bytes: int
    allowed_content_types: frozenset[str]

    def check(self, *, content_type: str, size_bytes: int) -> None:
        if content_type not in self.allowed_content_types:
            allowed = ", ".join(sorted(self.allowed_content_types))
            raise UploadRejected(
                f"content type {content_type!r} is not allowed: {allowed}"
            )
        if size_bytes > self.max_size_bytes:
            raise UploadRejected(f"file exceeds the {self.max_size_bytes}-byte limit")
