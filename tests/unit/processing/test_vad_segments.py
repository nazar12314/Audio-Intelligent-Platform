import pytest

from audio_platform.modules.processing.domain import (
    WINDOW_SAMPLES,
    SpeechSegment,
    VadParameters,
    VadResult,
    speech_segments,
)

WINDOW_MS = 32  # 512 samples at 16 kHz
NO_PAD = VadParameters(speech_pad_ms=0)


def windows(*runs: tuple[float, int]) -> list[float]:
    """runs of (probability, number of 32 ms windows)."""
    return [p for p, count in runs for _ in range(count)]


def segments(
    probs: list[float], params: VadParameters = NO_PAD
) -> list[tuple[int, int]]:
    result = speech_segments(probs, len(probs) * WINDOW_SAMPLES, params)
    return [(s.start_ms, s.end_ms) for s in result]


def test_silence_has_no_speech() -> None:
    assert segments(windows((0.05, 100))) == []


def test_one_burst_of_speech() -> None:
    probs = windows((0.0, 10), (0.9, 20), (0.0, 10))
    assert segments(probs) == [(10 * WINDOW_MS, 30 * WINDOW_MS)]


def test_bursts_shorter_than_min_speech_are_dropped() -> None:
    probs = windows((0.0, 10), (0.9, 5), (0.0, 10))  # 160 ms < 250 ms
    assert segments(probs) == []


def test_pauses_shorter_than_min_silence_do_not_split() -> None:
    probs = windows((0.9, 20), (0.0, 2), (0.9, 20), (0.0, 10))  # 64 ms pause
    assert segments(probs) == [(0, 42 * WINDOW_MS)]


def test_pauses_longer_than_min_silence_split() -> None:
    probs = windows((0.9, 20), (0.0, 10), (0.9, 20), (0.0, 10))
    assert segments(probs) == [(0, 20 * WINDOW_MS), (30 * WINDOW_MS, 50 * WINDOW_MS)]


def test_probabilities_between_thresholds_keep_speech_going() -> None:
    # 0.4 is below threshold (0.5) but above the 0.35 release threshold.
    probs = windows((0.0, 5), (0.9, 10), (0.4, 20), (0.0, 10))
    assert segments(probs) == [(5 * WINDOW_MS, 35 * WINDOW_MS)]


def test_speech_until_the_end_is_closed_at_the_audio_length() -> None:
    probs = windows((0.0, 10), (0.9, 20))
    assert segments(probs) == [(10 * WINDOW_MS, 30 * WINDOW_MS)]


def test_segments_are_padded_within_the_audio() -> None:
    probs = windows((0.9, 20), (0.0, 20))
    padded = segments(probs, VadParameters(speech_pad_ms=30))
    assert padded == [(0, 20 * WINDOW_MS + 30)]


@pytest.mark.parametrize(
    ("segments_ms", "speech_ms", "ratio"),
    [([], 0, 0.0), ([(0, 500), (1000, 1500)], 1000, 0.5)],
)
def test_vad_result_summary(
    segments_ms: list[tuple[int, int]], speech_ms: int, ratio: float
) -> None:
    result = VadResult(2000, [SpeechSegment(a, b) for a, b in segments_ms])
    assert (result.speech_ms, result.speech_ratio) == (speech_ms, ratio)
    assert result.speech_detected is bool(segments_ms)
