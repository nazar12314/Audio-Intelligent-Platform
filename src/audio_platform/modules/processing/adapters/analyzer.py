"""
Audio analysis = probe, validate, normalize, score speech. The subprocess variant
isolates it: a hung or crashing FFmpeg decode is killed without taking the worker
down, which a thread could not guarantee (Python cannot stop a thread).
"""

import asyncio
import multiprocessing
from collections.abc import Callable
from multiprocessing.connection import Connection
from pathlib import Path

from audio_platform.modules.processing.domain import (
    SAMPLE_RATE,
    AudioAnalysis,
    InvalidAudio,
    validate_audio,
)
from audio_platform.modules.processing.ports import (
    AnalysisTimedOut,
    AudioDecoder,
    SpeechProbabilityModel,
)


def analyze_audio(
    decoder: AudioDecoder,
    model: SpeechProbabilityModel,
    source: Path,
    target: Path,
    *,
    max_duration_s: int,
) -> AudioAnalysis:
    info = decoder.probe(source)
    validate_audio(info, max_duration_s=max_duration_s)
    samples = decoder.normalize(
        source,
        target,
        sample_rate=SAMPLE_RATE,
        max_samples=max_duration_s * SAMPLE_RATE,
    )
    return AudioAnalysis(info, samples, model.probabilities(target))


class InProcessAudioAnalyzer:
    """Runs in a worker thread; no time limit. For tests and trusted input."""

    def __init__(self, decoder: AudioDecoder, model: SpeechProbabilityModel) -> None:
        self._decoder = decoder
        self._model = model

    async def analyze(
        self, source: Path, target: Path, *, max_duration_s: int
    ) -> AudioAnalysis:
        return await asyncio.to_thread(
            analyze_audio,
            self._decoder,
            self._model,
            source,
            target,
            max_duration_s=max_duration_s,
        )


ChildFunction = Callable[[Connection, str, str, int], None]


def analyze_with_pyav_and_silero(
    conn: Connection, source: str, target: str, max_duration_s: int
) -> None:
    """Child process entry point: sends ("ok" | "invalid" | "error", payload)."""
    try:
        from audio_platform.modules.processing.adapters.pyav import PyAvDecoder
        from audio_platform.modules.processing.adapters.silero_onnx import (
            SileroOnnxModel,
        )

        analysis = analyze_audio(
            PyAvDecoder(),
            SileroOnnxModel(),
            Path(source),
            Path(target),
            max_duration_s=max_duration_s,
        )
        conn.send(("ok", analysis))
    except InvalidAudio as exc:
        conn.send(("invalid", str(exc)))
    except Exception as exc:
        conn.send(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        conn.close()


class SubprocessAudioAnalyzer:
    def __init__(
        self, timeout_s: float, child: ChildFunction = analyze_with_pyav_and_silero
    ) -> None:
        self._timeout_s = timeout_s
        self._child = child
        self._context = multiprocessing.get_context("spawn")  # no inherited state

    async def analyze(
        self, source: Path, target: Path, *, max_duration_s: int
    ) -> AudioAnalysis:
        receiver, sender = self._context.Pipe(duplex=False)
        process = self._context.Process(
            target=self._child,
            args=(sender, str(source), str(target), max_duration_s),
            daemon=True,
        )
        process.start()
        sender.close()  # the child holds the only write end; its exit means EOF
        try:
            await self._readable(receiver)
            try:
                kind, payload = receiver.recv()
            except EOFError:
                process.join(5)
                raise RuntimeError(
                    f"analysis process crashed (exit code {process.exitcode})"
                ) from None
        finally:
            # Also runs when the caller is cancelled: never leave a child behind.
            if process.is_alive():
                process.kill()
            await asyncio.to_thread(process.join, 5)
            receiver.close()

        if kind == "ok":
            analysis: AudioAnalysis = payload
            return analysis
        if kind == "invalid":
            raise InvalidAudio(payload)
        raise RuntimeError(payload)

    async def _readable(self, receiver: Connection) -> None:
        loop = asyncio.get_running_loop()
        ready = loop.create_future()

        def mark_ready() -> None:
            if not ready.done():
                ready.set_result(None)

        loop.add_reader(receiver.fileno(), mark_ready)
        try:
            async with asyncio.timeout(self._timeout_s):
                await ready
        except TimeoutError:
            raise AnalysisTimedOut(
                f"audio analysis exceeded {self._timeout_s:g} s"
            ) from None
        finally:
            loop.remove_reader(receiver.fileno())
