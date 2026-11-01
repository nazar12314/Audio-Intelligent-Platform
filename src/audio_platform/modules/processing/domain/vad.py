"""
Speech segments from Silero VAD probabilities. Ported from silero-vad 6.2.3
(`get_speech_timestamps_from_probs`, MIT) without the max-speech-duration
splitting, which only matters once long segments are fed to ASR.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field

SAMPLE_RATE = 16_000
WINDOW_SAMPLES = 512  # the 16 kHz model scores one 32 ms window per call


@dataclass(frozen=True, slots=True)
class VadParameters:
    threshold: float = 0.5
    min_speech_ms: int = 250
    min_silence_ms: int = 100
    speech_pad_ms: int = 30

    @property
    def neg_threshold(self) -> float:
        # Hysteresis: speech ends only once the probability drops well below threshold.
        return max(self.threshold - 0.15, 0.01)


@dataclass(frozen=True, slots=True)
class SpeechSegment:
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


@dataclass(frozen=True, slots=True)
class VadResult:
    duration_ms: int
    segments: list[SpeechSegment] = field(default_factory=list)

    @property
    def speech_ms(self) -> int:
        return sum(s.duration_ms for s in self.segments)

    @property
    def speech_detected(self) -> bool:
        return bool(self.segments)

    @property
    def speech_ratio(self) -> float:
        return round(self.speech_ms / self.duration_ms, 4) if self.duration_ms else 0.0


def speech_segments(
    probabilities: Sequence[float], audio_samples: int, params: VadParameters
) -> list[SpeechSegment]:
    min_speech = SAMPLE_RATE * params.min_speech_ms / 1000
    min_silence = SAMPLE_RATE * params.min_silence_ms / 1000
    pad = SAMPLE_RATE * params.speech_pad_ms / 1000

    spans: list[list[int]] = []
    triggered = False
    start = temp_end = 0
    for index, probability in enumerate(probabilities):
        sample = WINDOW_SAMPLES * index
        if probability >= params.threshold and temp_end:
            temp_end = 0
        if probability >= params.threshold and not triggered:
            triggered, start = True, sample
            continue
        if probability < params.neg_threshold and triggered:
            if not temp_end:
                temp_end = sample
            if sample - temp_end < min_silence:
                continue
            if temp_end - start > min_speech:
                spans.append([start, temp_end])
            triggered, temp_end = False, 0

    if triggered and audio_samples - start > min_speech:
        spans.append([start, audio_samples])

    for i, span in enumerate(spans):
        if i == 0:
            span[0] = int(max(0, span[0] - pad))
        if i != len(spans) - 1:
            gap = spans[i + 1][0] - span[1]
            if gap < 2 * pad:
                span[1] += int(gap // 2)
                spans[i + 1][0] = int(max(0, spans[i + 1][0] - gap // 2))
            else:
                span[1] = int(min(audio_samples, span[1] + pad))
                spans[i + 1][0] = int(max(0, spans[i + 1][0] - pad))
        else:
            span[1] = int(min(audio_samples, span[1] + pad))

    return [
        SpeechSegment(start * 1000 // SAMPLE_RATE, end * 1000 // SAMPLE_RATE)
        for start, end in spans
    ]
