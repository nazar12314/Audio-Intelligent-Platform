from bisect import bisect_right
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import accumulate
from math import ceil

from audio_platform.modules.processing.domain.vad import SpeechSegment

# Whisper hears 30 s at a time. Speech that fills nearly all of it makes Whisper leave
# the last sentence unfinished, which a batched decode then drops; shorter windows
# leave it room to finish.
WINDOW_MS = 20_000
# Segments join across a pause only while a sentence is still going, and never across
# a pause longer than this: a missing full stop must not swallow a long silence.
JOIN_PAUSE_MS = 1500
# Full stop, question and exclamation marks, ellipsis; also their CJK forms.
_SENTENCE_END = (".", "?", "!", "\u2026", "\u3002", "\uff1f", "\uff01")
_CLOSING = "\"')]\u00bb\u201d\u2019"  # quotes and brackets after the mark


@dataclass(frozen=True, slots=True)
class Word:
    start_ms: int
    end_ms: int
    text: str  # as Whisper wrote it, leading space included
    probability: float


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """
    Whole VAD speech segments holding whole sentences: from the start of the first
    segment to the end of the last.
    """

    start_ms: int
    end_ms: int
    text: str  # empty when no words were recognized in the segment
    words: list[Word] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Transcript:
    language: str
    language_probability: float
    segments: list[TranscriptSegment] = field(default_factory=list)

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.segments if s.text)


def speech_windows(
    speech: Sequence[SpeechSegment], max_ms: int = WINDOW_MS
) -> list[SpeechSegment]:
    """
    Consecutive speech packed into windows of at most `max_ms` of the recording,
    pauses between segments included; a longer segment is cut into equal pieces.
    Each window is transcribed on its own, so windows can be decoded as a batch.
    """
    windows: list[SpeechSegment] = []
    for segment in speech:
        pieces = ceil(segment.duration_ms / max_ms)
        for i in range(pieces):
            start = segment.start_ms + segment.duration_ms * i // pieces
            end = segment.start_ms + segment.duration_ms * (i + 1) // pieces
            if windows and end - windows[-1].start_ms <= max_ms:
                windows[-1] = SpeechSegment(windows[-1].start_ms, end)
            else:
                windows.append(SpeechSegment(start, end))
    return windows


class SpeechTimeline:
    """
    The windows played back to back, which is all the transcriber hears. Maps
    times on that timeline back to the recording.
    """

    def __init__(self, windows: Sequence[SpeechSegment]) -> None:
        self._windows = list(windows)
        self._ends = list(accumulate(w.duration_ms for w in self._windows))

    @property
    def duration_ms(self) -> int:
        return self._ends[-1] if self._ends else 0

    def window_offsets_ms(self) -> list[tuple[int, int]]:
        """Each window's (start, end) on the transcriber's timeline."""
        return [
            (end - w.duration_ms, end)
            for w, end in zip(self._windows, self._ends, strict=True)
        ]

    def window_of(self, start_ms: float, end_ms: float) -> int:
        """The window a span lies in: the one holding its middle."""
        if not self._windows:
            raise ValueError("the timeline has no speech")
        index = bisect_right(self._ends, (start_ms + end_ms) / 2)
        return min(index, len(self._windows) - 1)

    def to_recording_span(
        self, start_ms: float, end_ms: float, *, window: int | None = None
    ) -> tuple[int, int]:
        """
        Map a span into its window, or into `window` when given: a word's timing can
        stray a few ms past its window's start, so words follow their Whisper
        segment's window rather than their own.
        """
        index = self.window_of(start_ms, end_ms) if window is None else window
        window_span = self._windows[index]
        offset = self._ends[index] - window_span.duration_ms

        def in_window(ms: float) -> int:
            moved = window_span.start_ms + round(ms - offset)
            return min(max(moved, window_span.start_ms), window_span.end_ms)

        start, end = in_window(start_ms), in_window(end_ms)
        return start, max(start, end)


def transcript_segments(
    speech: Sequence[SpeechSegment], words: Sequence[Word]
) -> list[TranscriptSegment]:
    """
    The segments VAD and Whisper agree on: whole speech segments holding whole
    sentences. Every word goes to the speech segment it was spoken in (the nearest
    one when its timing puts it in a pause). A speech segment joins the next while
    its last word does not end a sentence and the pause between them is at most
    JOIN_PAUSE_MS. Speech without words keeps a segment of its own with empty text.
    """
    starts = [s.start_ms for s in speech]
    spoken: list[list[Word]] = [[] for _ in speech]
    for word in words:
        middle = (word.start_ms + word.end_ms) / 2
        index = max(bisect_right(starts, middle) - 1, 0)
        following = index + 1
        if (
            middle > speech[index].end_ms
            and following < len(speech)
            and speech[following].start_ms - middle < middle - speech[index].end_ms
        ):
            index = following
        spoken[index].append(word)
    for group in spoken:
        group.sort(key=lambda w: w.start_ms)

    def continues(index: int) -> bool:
        following = index + 1
        return (
            following < len(speech)
            and bool(spoken[index])
            and bool(spoken[following])
            and not _ends_sentence(spoken[index][-1].text)
            and speech[following].start_ms - speech[index].end_ms <= JOIN_PAUSE_MS
        )

    segments: list[TranscriptSegment] = []
    first = 0
    for index, segment in enumerate(speech):
        if continues(index):
            continue
        words_in = [w for group in spoken[first : index + 1] for w in group]
        segments.append(
            TranscriptSegment(
                start_ms=speech[first].start_ms,
                end_ms=segment.end_ms,
                text="".join(w.text for w in words_in).strip(),
                words=words_in,
            )
        )
        first = index + 1
    return segments


def _ends_sentence(text: str) -> bool:
    return text.rstrip().rstrip(_CLOSING).endswith(_SENTENCE_END)


def unheard_window_ends(
    windows: Sequence[SpeechSegment],
    segments: Sequence[TranscriptSegment],
    *,
    min_ms: int = 1000,
) -> list[SpeechSegment]:
    """
    Speech of at least `min_ms` at the end of a window that got no words: Whisper
    may have left a sentence it thought ran past the end unfinished, and a batched
    decode never comes back for it (see WINDOW_MS). Transcribed again on its own as
    a safety net. Shorter bursts are mostly breaths and grunts VAD let through, whose
    text was dropped as hallucinated; decoding them again only costs time.
    """
    unheard: list[SpeechSegment] = []
    for window in windows:
        inside = [s for s in segments if window.start_ms <= s.start_ms < window.end_ms]
        tail: list[SpeechSegment] = []
        for segment in reversed(inside):
            if segment.text:
                break
            if segment.end_ms - segment.start_ms >= min_ms:
                tail.append(SpeechSegment(segment.start_ms, segment.end_ms))
        unheard.extend(reversed(tail))
    return unheard
