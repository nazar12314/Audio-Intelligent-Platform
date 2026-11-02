"""
The Faster-Whisper adapter around a fake batched pipeline: what it asks Whisper to
decode and what it does with the answer. The real model runs in
tests/integration/test_whisper_transcriber.py.
"""

import asyncio
import threading
import time
import wave
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from audio_platform.modules.processing.adapters.whisper_asr import (
    FasterWhisperTranscriber,
    WhisperOptions,
    hallucinated,
)
from audio_platform.modules.processing.domain import InvalidAudio, SpeechSegment
from audio_platform.modules.processing.ports import AnalysisTimedOut

S = SpeechSegment
OPTIONS = WhisperOptions(
    model="medium",
    device="cpu",
    compute_type="int8",
    cpu_threads=1,
    download_dir=None,
    beam_size=5,
    batch_size=8,
    language=None,
    timeout_s=60,
)
INFO = SimpleNamespace(language="en", language_probability=0.98)


def word(start: float, end: float, text: str, probability: float = 0.95) -> Any:
    return SimpleNamespace(start=start, end=end, word=text, probability=probability)


def segment(*words: Any, no_speech: float = 0.01) -> Any:
    return SimpleNamespace(
        start=words[0].start if words else 0.0,
        end=words[-1].end if words else 0.0,
        words=list(words),
        no_speech_prob=no_speech,
    )


class FakePipeline:
    """Answers each `transcribe` call with the next scripted list of segments."""

    def __init__(self, *answers: list[Any]) -> None:
        self.answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    def transcribe(self, audio: Any, **options: Any) -> tuple[Iterator[Any], Any]:
        self.calls.append({"samples": len(audio), **options})
        return iter(self.answers.pop(0)), INFO


@pytest.fixture
def wav(tmp_path: Path) -> Path:
    path = tmp_path / "normalized.wav"
    with wave.open(str(path), "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16_000)
        out.writeframes(b"\x00\x00" * 16_000 * 4)
    return path


async def test_words_land_in_the_recording_and_hallucinations_are_dropped(
    wav: Path,
) -> None:
    pipeline = FakePipeline(
        [
            # Heard time: the window 1000-3000 ms starts at 0.
            segment(word(0.1, 0.5, " Hello"), word(0.5, 0.9, " there.")),
            segment(word(1.6, 1.9, " Thanks for watching!"), no_speech=0.79),
        ]
    )
    transcriber = FasterWhisperTranscriber(pipeline, OPTIONS)

    transcript = await transcriber.transcribe(wav, [S(1000, 2000), S(2500, 3000)])

    assert [(s.start_ms, s.end_ms, s.text) for s in transcript.segments] == [
        (1000, 2000, "Hello there."),
        (2500, 3000, ""),  # too short to decode again
    ]
    assert [(w.start_ms, w.end_ms) for w in transcript.segments[0].words] == [
        (1100, 1500),
        (1500, 1900),
    ]
    [call] = pipeline.calls
    assert call["clip_timestamps"] == [{"start": 0.0, "end": 2.0}]
    assert (call["samples"], call["language"]) == (32_000, None)
    assert (call["word_timestamps"], call["batch_size"]) == (True, 8)
    assert (transcript.language, transcript.language_probability) == ("en", 0.98)


async def test_a_silent_window_end_is_decoded_again_in_the_detected_language(
    wav: Path,
) -> None:
    pipeline = FakePipeline(
        [segment(word(0.1, 0.9, " First."))],
        [segment(word(0.2, 1.2, " Second."))],  # the 1500-3000 ms tail on its own
    )
    transcriber = FasterWhisperTranscriber(pipeline, OPTIONS)

    transcript = await transcriber.transcribe(wav, [S(0, 1000), S(1500, 3000)])

    assert [s.text for s in transcript.segments] == ["First.", "Second."]
    assert pipeline.calls[1]["clip_timestamps"] == [{"start": 0.0, "end": 1.5}]
    assert pipeline.calls[1]["language"] == "en"


async def test_the_time_limit_stops_decoding(wav: Path) -> None:
    def slow() -> Iterator[Any]:
        time.sleep(0.05)
        yield segment(word(0.1, 0.5, " Late."))

    pipeline = FakePipeline([])
    pipeline.transcribe = lambda audio, **options: (slow(), INFO)  # type: ignore[method-assign]
    transcriber = FasterWhisperTranscriber(pipeline, replace(OPTIONS, timeout_s=0.01))

    with pytest.raises(AnalysisTimedOut, match=r"exceeded 0\.01 s"):
        await transcriber.transcribe(wav, [S(0, 1000)])


async def test_a_caller_giving_up_stops_the_decoding_thread(wav: Path) -> None:
    first_done, release, closed = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    requested: list[int] = []

    def blocking() -> Iterator[Any]:
        try:
            for n in range(1, 4):
                requested.append(n)
                yield segment(word(0.1, 0.5, f" Part {n}."))
                if n == 1:
                    first_done.set()
                    release.wait(5)
        finally:
            closed.set()

    pipeline = FakePipeline([])
    pipeline.transcribe = lambda audio, **options: (blocking(), INFO)  # type: ignore[method-assign]
    transcriber = FasterWhisperTranscriber(pipeline, OPTIONS)

    task = asyncio.create_task(transcriber.transcribe(wav, [S(0, 1000)]))
    assert await asyncio.to_thread(first_done.wait, 5)
    task.cancel()  # e.g. the message handling timed out
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()

    assert await asyncio.to_thread(closed.wait, 5)
    assert requested == [1, 2]  # stopped before asking Whisper for more


async def test_recordings_without_speech_are_invalid(wav: Path) -> None:
    transcriber = FasterWhisperTranscriber(FakePipeline(), OPTIONS)

    with pytest.raises(InvalidAudio, match="no speech"):
        await transcriber.transcribe(wav, [])


async def test_only_normalized_audio_is_accepted(tmp_path: Path) -> None:
    stereo = tmp_path / "stereo.wav"
    with wave.open(str(stereo), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(44_100)
        out.writeframes(b"\x00\x00\x00\x00" * 100)
    transcriber = FasterWhisperTranscriber(FakePipeline([]), OPTIONS)

    with pytest.raises(ValueError, match="16 kHz mono"):
        await transcriber.transcribe(stereo, [S(0, 1000)])


def filtered(no_speech: float, *probabilities: float) -> Any:
    words = [SimpleNamespace(probability=p) for p in probabilities]
    return SimpleNamespace(no_speech_prob=no_speech, words=words)


@pytest.mark.parametrize(
    ("whisper", "dropped"),
    [
        # Values from a 13-minute gym video transcribed with `medium`.
        (filtered(0.79, 0.95, 0.6, 0.3), True),  # "Thanks for watching!" over a grunt
        (filtered(0.08, 0.29), True),  # "Oh." with no confident word
        (filtered(0.0), True),  # no words at all
        (filtered(0.39, 0.45, 0.9, 0.2), False),  # real, if unsure, speech
        (filtered(0.03, 0.99, 0.97), False),
    ],
)
def test_hallucinations_are_recognized(whisper: Any, dropped: bool) -> None:
    assert hallucinated(whisper) is dropped
