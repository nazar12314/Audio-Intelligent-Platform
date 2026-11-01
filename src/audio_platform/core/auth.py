import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from audio_platform.core.exceptions import Unauthorized


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: uuid.UUID


class Authenticator(Protocol):
    async def authenticate(self, headers: Mapping[str, str]) -> Principal:
        """Return the caller, or raise Unauthorized."""
        ...


class DevHeaderAuthenticator:
    """
    Trusts the user ID sent by the client. Development only: settings refuse it
    when env=prod.
    """

    header = "X-Dev-User-Id"

    async def authenticate(self, headers: Mapping[str, str]) -> Principal:
        raw = headers.get(self.header)
        if not raw:
            raise Unauthorized(f"missing {self.header} header")
        try:
            return Principal(user_id=uuid.UUID(raw))
        except ValueError:
            raise Unauthorized(f"{self.header} must be a UUID") from None
