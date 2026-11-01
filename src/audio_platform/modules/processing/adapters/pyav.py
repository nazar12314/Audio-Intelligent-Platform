import wave
from pathlib import Path

import av
import av.error

from audio_platform.modules.processing.domain import AudioInfo, InvalidAudio


def _describe(exc: av.error.FFmpegError) -> str:
    # str(exc) embeds the worker's temp file path; clients only need the reason.
    return exc.strerror or type(exc).__name__


class PyAvDecoder:
    """
    Decodes any container FFmpeg understands (bundled with the PyAV wheel).
    """

    def probe(self, path: Path) -> AudioInfo:
        try:
            with av.open(str(path)) as container:
                if not container.streams.audio:
                    raise InvalidAudio("no audio stream")
                stream = container.streams.audio[0]
                duration = None

                if stream.duration is not None and stream.time_base is not None:
                    duration = float(stream.duration * stream.time_base)
                elif container.duration is not None:
                    duration = container.duration / av.time_base
                return AudioInfo(
                    container=container.format.name,
                    codec=stream.codec_context.name,
                    sample_rate=stream.codec_context.sample_rate or 0,
                    channels=stream.codec_context.channels or 0,
                    duration_s=duration,
                )
        except av.error.FFmpegError as exc:
            raise InvalidAudio(f"unreadable file: {_describe(exc)}") from None

    def normalize(
        self, source: Path, target: Path, *, sample_rate: int, max_samples: int
    ) -> int:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=sample_rate)
        written = 0
        try:
            with av.open(str(source)) as container, wave.open(str(target), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(sample_rate)

                def write(frames: list[av.AudioFrame]) -> None:
                    nonlocal written
                    for frame in frames:
                        pcm = frame.to_ndarray().tobytes()
                        written += frame.samples
                        if written > max_samples:
                            raise InvalidAudio(
                                f"audio exceeds {max_samples // sample_rate} s"
                            )
                        wav.writeframes(pcm)

                for frame in container.decode(audio=0):
                    write(resampler.resample(frame))
                write(resampler.resample(None))  # flush buffered samples
        except av.error.FFmpegError as exc:
            raise InvalidAudio(f"cannot decode audio: {_describe(exc)}") from None
        if written == 0:
            raise InvalidAudio("no decodable audio")
        return written
