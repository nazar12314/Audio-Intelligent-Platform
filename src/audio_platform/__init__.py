"""Audio Intelligence Platform backend."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("audio-platform")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without installing
    __version__ = "0.0.0"

__all__ = ["__version__"]
