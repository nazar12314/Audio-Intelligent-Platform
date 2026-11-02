"""
Faster-Whisper on CTranslate2. The model is loaded once per worker process and
kept in memory. Speech is packed into windows of up to 20 s (WINDOW_MS) that are
decoded in batches. Transcription runs in a worker thread and stops between batches
when its time limit passes or its caller gives up.
"""

import asyncio
import threading
import time
import wave
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from faster_whisper import BatchedInferencePipeline, WhisperModel

from audio_platform.modules.processing.domain import (
    SAMPLE_RATE,
    InvalidAudio,
    SpeechSegment,
    SpeechTimeline,
    Transcript,
    Word,
    speech_windows,
    transcript_segments,
    unheard_window_ends,
)
from audio_platform.modules.processing.ports import AnalysisTimedOut

_SAMPLES_PER_MS = SAMPLE_RATE // 1000
# Whisper's own "this window is not speech" threshold (its no_speech_threshold).
_NO_SPEECH = 0.6
# A segment with no word this likely is noise written down as a filler ("Oh.").
_CONFIDENT_WORD = 0.5


@dataclass(frozen=True, slots=True)
class WhisperOptions:
    model: str  # size ("small", "large-v3", ...) or a local CTranslate2 model dir
    device: str
    compute_type: str
    cpu_threads: int
    download_dir: str | None
    beam_size: int
    batch_size: int  # windows decoded together
    language: str | None  # None: detect it
    timeout_s: float


class FasterWhisperTranscriber:
    def __init__(self, pipeline: Any, options: WhisperOptions) -> None:
        """`pipeline`: a Faster-Whisper BatchedInferencePipeline; see `load`."""
        self._pipeline = pipeline
        self._options = options

    @classmethod
    def load(cls, options: WhisperOptions) -> FasterWhisperTranscriber:
        """Blocking: downloads the model on first use, then loads it."""
        model = WhisperModel(
            options.model,
            device=options.device,
            compute_type=options.compute_type,
            cpu_threads=options.cpu_threads,
            download_root=options.download_dir,
        )
        return cls(BatchedInferencePipeline(model), options)

    async def transcribe(
        self, wav_path: Path, speech: Sequence[SpeechSegment]
    ) -> Transcript:
        cancelled = threading.Event()
        try:
            return await asyncio.to_thread(
                self._transcribe, wav_path, speech, cancelled
            )
        finally:
            cancelled.set()  # stops the thread if its caller gave up first

    def _transcribe(
        self,
        wav_path: Path,
        speech: Sequence[SpeechSegment],
        cancelled: threading.Event,
    ) -> Transcript:
        if not speech:
            raise InvalidAudio("no speech to transcribe")
        deadline = time.monotonic() + self._options.timeout_s
        windows = speech_windows(speech)
        words, info = self._decode(
            wav_path, windows, self._options.language, deadline, cancelled
        )
        segments = transcript_segments(speech, words)

        unheard = unheard_window_ends(windows, segments)
        if unheard:
            again, _ = self._decode(
                wav_path, speech_windows(unheard), info.language, deadline, cancelled
            )
            segments = transcript_segments(speech, words + again)

        return Transcript(
            language=info.language,
            language_probability=info.language_probability,
            segments=segments,
        )

    def _decode(
        self,
        wav_path: Path,
        windows: Sequence[SpeechSegment],
        language: str | None,
        deadline: float,
        cancelled: threading.Event,
    ) -> tuple[list[Word], Any]:
        """
        The words Whisper heard, in recording time, without likely hallucinations.
        """
        timeline = SpeechTimeline(windows)
        decoded, info = self._pipeline.transcribe(
            _read(wav_path, windows),
            clip_timestamps=[
                {"start": start / 1000, "end": end / 1000}
                for start, end in timeline.window_offsets_ms()
            ],
            language=language,
            beam_size=self._options.beam_size,
            batch_size=self._options.batch_size,
            without_timestamps=False,
            # Words are placed onto the VAD segments, so transcript segments are made
            # of whole speech segments.
            word_timestamps=True,
        )
        words: list[Word] = []

        for segment in decoded:
            if cancelled.is_set():
                raise RuntimeError("transcription abandoned by its caller")
            if time.monotonic() > deadline:
                raise AnalysisTimedOut(
                    f"transcription exceeded {self._options.timeout_s:g} s"
                )
            if hallucinated(segment):
                continue
            window = timeline.window_of(segment.start * 1000, segment.end * 1000)
            for word in segment.words:
                start, end = timeline.to_recording_span(
                    word.start * 1000, word.end * 1000, window=window
                )
                words.append(Word(start, end, word.word, word.probability))
        return words, info


def hallucinated(segment: Any) -> bool:
    """
    Text Whisper wrote over something that is not speech: either it judged the whole
    window not to be speech (in batches, no_speech_prob is per window), or no word in
    the segment is likely.
    """
    if not segment.words:
        return True

    no_speech: float = segment.no_speech_prob
    best_word: float = max(w.probability for w in segment.words)

    return no_speech > _NO_SPEECH or best_word < _CONFIDENT_WORD


def _read(path: Path, windows: Sequence[SpeechSegment]) -> Any:
    """
    The windows of a 16 kHz mono WAV, back to back, as one float32 array.
    """
    with wave.open(str(path), "rb") as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
            SAMPLE_RATE,
            1,
            2,
        ):
            raise ValueError("expected 16 kHz mono 16-bit PCM")
        frames = wav.getnframes()
        clips = []

        for window in windows:
            wav.setpos(min(window.start_ms * _SAMPLES_PER_MS, frames))
            clips.append(wav.readframes(window.duration_ms * _SAMPLES_PER_MS))
    pcm = np.frombuffer(b"".join(clips), dtype="<i2")

    return pcm.astype(np.float32) / 32768.0
