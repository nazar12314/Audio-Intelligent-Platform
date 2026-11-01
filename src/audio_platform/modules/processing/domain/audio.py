from dataclasses import dataclass


class InvalidAudio(Exception):
    """The file cannot be processed; retrying will not help."""


@dataclass(frozen=True, slots=True)
class AudioInfo:
    container: str
    codec: str
    sample_rate: int
    channels: int
    duration_s: float | None  # some containers only know it after a full decode


@dataclass(frozen=True, slots=True)
class AudioAnalysis:
    info: AudioInfo
    samples: int  # of the normalized 16 kHz mono audio
    probabilities: list[float]  # speech probability per 512-sample window


def validate_audio(info: AudioInfo, *, max_duration_s: int) -> None:
    if info.sample_rate <= 0 or info.channels <= 0:
        raise InvalidAudio("audio stream has no samples")
    if info.duration_s is not None and info.duration_s <= 0:
        raise InvalidAudio("audio is empty")
    if info.duration_s is not None and info.duration_s > max_duration_s:
        raise InvalidAudio(
            f"audio is {info.duration_s:.0f} s long; the limit is {max_duration_s} s"
        )
