"""PyAV and Silero adapters on real audio; fixtures are generated speech and silence."""

import wave
from pathlib import Path

import av
import numpy as np
import pytest

from audio_platform.modules.processing.adapters.pyav import PyAvDecoder
from audio_platform.modules.processing.adapters.silero_onnx import SileroOnnxModel
from audio_platform.modules.processing.domain import (
    InvalidAudio,
    VadParameters,
    speech_segments,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "audio"
SPEECH = FIXTURES / "speech_16k_mono.wav"  # 1 s silence, ~7 s speech, 1 s silence
SILENCE = FIXTURES / "silence_16k_mono.wav"


def _encode(source: Path, target: Path, codec: str, rate: int, layout: str) -> Path:
    """Re-encode the speech fixture to another container/codec/rate/layout."""
    with av.open(str(source)) as src, av.open(str(target), "w") as dst:
        stream = dst.add_stream(codec, rate=rate, layout=layout)
        assert isinstance(stream, av.AudioStream)
        resampler = av.AudioResampler(
            format=stream.codec_context.format, layout=layout, rate=rate
        )
        for frame in src.decode(audio=0):
            for out in resampler.resample(frame):
                dst.mux(stream.encode(out))
        for out in resampler.resample(None):
            dst.mux(stream.encode(out))
        dst.mux(stream.encode(None))
    return target


@pytest.fixture(scope="module")
def model() -> SileroOnnxModel:
    return SileroOnnxModel()


def _segments(model: SileroOnnxModel, wav: Path) -> list[tuple[int, int]]:
    with wave.open(str(wav)) as w:
        samples = w.getnframes()
    found = speech_segments(model.probabilities(wav), samples, VadParameters())
    return [(s.start_ms, s.end_ms) for s in found]


def test_silero_finds_the_speech_between_the_silences(model: SileroOnnxModel) -> None:
    found = _segments(model, SPEECH)

    assert found, "no speech detected"
    assert 800 <= found[0][0] <= 1600
    assert 7500 <= found[-1][1] <= 8400


def test_silero_finds_no_speech_in_silence(model: SileroOnnxModel) -> None:
    assert _segments(model, SILENCE) == []


@pytest.mark.parametrize(
    ("name", "codec", "rate", "layout"),
    [
        ("speech.mp3", "libmp3lame", 44_100, "stereo"),
        ("speech.flac", "flac", 48_000, "stereo"),
        ("speech.ogg", "libopus", 48_000, "mono"),
        ("speech.m4a", "aac", 22_050, "mono"),
    ],
)
def test_any_supported_format_normalizes_to_16k_mono(
    tmp_path: Path,
    model: SileroOnnxModel,
    name: str,
    codec: str,
    rate: int,
    layout: str,
) -> None:
    source = _encode(SPEECH, tmp_path / name, codec, rate, layout)
    decoder = PyAvDecoder()

    info = decoder.probe(source)
    target = tmp_path / "normalized.wav"
    samples = decoder.normalize(source, target, sample_rate=16_000, max_samples=10**8)

    assert (info.sample_rate, info.channels) == (rate, 2 if layout == "stereo" else 1)
    with wave.open(str(target)) as wav:
        assert (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) == (
            16_000,
            1,
            2,
        )
        assert wav.getnframes() == samples
    assert abs(samples / 16_000 - 9.07) < 0.2
    assert _segments(model, target), f"speech lost after {codec} round trip"


def test_unreadable_files_are_invalid(tmp_path: Path) -> None:
    junk = tmp_path / "notes.mp3"
    junk.write_bytes(b"this is not audio" * 100)

    with pytest.raises(InvalidAudio) as error:
        PyAvDecoder().probe(junk)

    assert (
        str(error.value) == "unreadable file: Invalid data found when processing input"
    )
    assert str(tmp_path) not in str(error.value)


def test_files_without_audio_streams_are_invalid(tmp_path: Path) -> None:
    video = tmp_path / "video.mp4"
    with av.open(str(video), "w") as container:
        stream = container.add_stream("mpeg4", rate=1)
        stream.width = stream.height = 16
        frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), np.uint8), "rgb24")
        container.mux(stream.encode(frame.reformat(format=stream.pix_fmt)))
        container.mux(stream.encode(None))

    with pytest.raises(InvalidAudio, match="no audio stream"):
        PyAvDecoder().probe(video)


def test_normalization_stops_at_the_duration_limit(tmp_path: Path) -> None:
    with pytest.raises(InvalidAudio, match="exceeds"):
        PyAvDecoder().normalize(
            SPEECH, tmp_path / "out.wav", sample_rate=16_000, max_samples=16_000 * 5
        )
