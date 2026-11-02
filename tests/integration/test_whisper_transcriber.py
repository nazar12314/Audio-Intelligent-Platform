"""
Faster-Whisper on the speech fixture. Integration: the first run downloads the
`tiny` model (~75 MB) into the Hugging Face cache.
"""

import wave
from dataclasses import replace
from pathlib import Path

import pytest

from audio_platform.modules.processing.adapters.silero_onnx import SileroOnnxModel
from audio_platform.modules.processing.adapters.whisper_asr import (
    FasterWhisperTranscriber,
    WhisperOptions,
)
from audio_platform.modules.processing.domain import (
    SpeechSegment,
    VadParameters,
    speech_segments,
)
from audio_platform.modules.processing.ports import AnalysisTimedOut

pytestmark = pytest.mark.integration

SPEECH = Path(__file__).parents[1] / "fixtures" / "audio" / "speech_16k_mono.wav"
OPTIONS = WhisperOptions(
    model="tiny",
    device="cpu",
    compute_type="int8",
    cpu_threads=2,
    download_dir=None,
    beam_size=1,
    batch_size=4,
    language=None,
    timeout_s=120,
)


@pytest.fixture(scope="module")
def transcriber() -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber.load(OPTIONS)


@pytest.fixture(scope="module")
def speech() -> list[SpeechSegment]:
    with wave.open(str(SPEECH)) as wav:
        samples = wav.getnframes()
    probabilities = SileroOnnxModel().probabilities(SPEECH)
    return speech_segments(probabilities, samples, VadParameters())


async def test_speech_is_transcribed_with_language_and_recording_times(
    transcriber: FasterWhisperTranscriber, speech: list[SpeechSegment]
) -> None:
    transcript = await transcriber.transcribe(SPEECH, speech)

    assert transcript.language == "en"
    assert transcript.language_probability > 0.5
    assert "audio intelligence platform" in transcript.text.lower()
    # Transcript segments are whole VAD segments: together they cover every one.
    covered = [
        s
        for segment in transcript.segments
        for s in speech
        if segment.start_ms <= s.start_ms and s.end_ms <= segment.end_ms
    ]
    assert covered == speech
    assert {s.start_ms for s in transcript.segments} <= {s.start_ms for s in speech}
    assert {s.end_ms for s in transcript.segments} <= {s.end_ms for s in speech}
    for segment in transcript.segments:
        assert segment.text
        assert all(
            segment.start_ms <= word.start_ms <= word.end_ms <= segment.end_ms
            for word in segment.words
        )


async def test_a_forced_language_skips_detection(
    speech: list[SpeechSegment],
) -> None:
    forced = FasterWhisperTranscriber.load(replace(OPTIONS, language="en"))

    transcript = await forced.transcribe(SPEECH, speech)

    assert (transcript.language, transcript.language_probability) == ("en", 1)


async def test_the_time_limit_stops_transcription(
    speech: list[SpeechSegment],
) -> None:
    hurried = FasterWhisperTranscriber.load(replace(OPTIONS, timeout_s=0))

    with pytest.raises(AnalysisTimedOut, match="exceeded 0 s"):
        await hurried.transcribe(SPEECH, speech)
