import asyncio
import time
from pathlib import Path

import pytest

from audio_platform.modules.processing.adapters.analyzer import (
    InProcessAudioAnalyzer,
    SubprocessAudioAnalyzer,
)
from audio_platform.modules.processing.adapters.pyav import PyAvDecoder
from audio_platform.modules.processing.adapters.silero_onnx import SileroOnnxModel
from audio_platform.modules.processing.domain import InvalidAudio
from audio_platform.modules.processing.ports import AnalysisTimedOut
from tests.unit.processing import child_behaviours

SPEECH = Path(__file__).parents[2] / "fixtures" / "audio" / "speech_16k_mono.wav"


async def test_matches_the_in_process_analysis(tmp_path: Path) -> None:
    isolated = await SubprocessAudioAnalyzer(timeout_s=60).analyze(
        SPEECH, tmp_path / "a.wav", max_duration_s=3600
    )
    local = await InProcessAudioAnalyzer(PyAvDecoder(), SileroOnnxModel()).analyze(
        SPEECH, tmp_path / "b.wav", max_duration_s=3600
    )

    assert isolated == local
    assert (tmp_path / "a.wav").read_bytes() == (tmp_path / "b.wav").read_bytes()


async def test_invalid_audio_is_reported_as_invalid(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio" * 100)

    with pytest.raises(InvalidAudio, match="unreadable file"):
        await SubprocessAudioAnalyzer(timeout_s=60).analyze(
            junk, tmp_path / "out.wav", max_duration_s=3600
        )


async def test_a_hung_analysis_is_killed_at_the_deadline(tmp_path: Path) -> None:
    analyzer = SubprocessAudioAnalyzer(timeout_s=1, child=child_behaviours.hang)
    started = time.monotonic()

    with pytest.raises(AnalysisTimedOut, match="exceeded 1 s"):
        await analyzer.analyze(SPEECH, tmp_path / "out.wav", max_duration_s=3600)

    assert time.monotonic() - started < 10
    assert not _children_alive()


async def test_a_crashing_analysis_does_not_take_the_worker_down(
    tmp_path: Path,
) -> None:
    analyzer = SubprocessAudioAnalyzer(timeout_s=30, child=child_behaviours.crash)

    with pytest.raises(RuntimeError, match="exit code 3"):
        await analyzer.analyze(SPEECH, tmp_path / "out.wav", max_duration_s=3600)


async def test_cancelling_the_caller_kills_the_child(tmp_path: Path) -> None:
    analyzer = SubprocessAudioAnalyzer(timeout_s=3600, child=child_behaviours.hang)
    task = asyncio.create_task(
        analyzer.analyze(SPEECH, tmp_path / "out.wav", max_duration_s=3600)
    )
    await asyncio.sleep(1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not _children_alive()


def _children_alive() -> bool:
    import multiprocessing

    return any(p.is_alive() for p in multiprocessing.active_children())
