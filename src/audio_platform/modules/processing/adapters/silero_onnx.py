import wave
from importlib import resources
from pathlib import Path

import numpy as np
import onnxruntime

from audio_platform.modules.processing.domain import SAMPLE_RATE, WINDOW_SAMPLES

_CONTEXT_SAMPLES = 64  # the model sees the tail of the previous window
_READ_WINDOWS = 1024


class SileroOnnxModel:
    """
    Silero VAD 16 kHz on onnxruntime, mirroring the
    reference OnnxWrapper: recurrent state and context carry across windows.
    """

    def __init__(self) -> None:
        model = resources.files(__package__) / "silero" / "silero_vad_16k.onnx"
        options = onnxruntime.SessionOptions()
        # One thread per inference; scale out with more worker processes instead.
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            model.read_bytes(), sess_options=options, providers=["CPUExecutionProvider"]
        )

    def probabilities(self, wav_path: Path) -> list[float]:
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, _CONTEXT_SAMPLES), dtype=np.float32)
        sample_rate = np.array(SAMPLE_RATE, dtype=np.int64)
        probabilities: list[float] = []

        with wave.open(str(wav_path), "rb") as wav:
            if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth()) != (
                SAMPLE_RATE,
                1,
                2,
            ):
                raise ValueError("expected 16 kHz mono 16-bit PCM")
            while chunk := wav.readframes(WINDOW_SAMPLES * _READ_WINDOWS):
                samples = np.frombuffer(chunk, dtype="<i2").astype(np.float32) / 32768.0
                remainder = len(samples) % WINDOW_SAMPLES

                if remainder:
                    samples = np.pad(samples, (0, WINDOW_SAMPLES - remainder))
                for window in samples.reshape(-1, WINDOW_SAMPLES):
                    model_input = np.concatenate(
                        [context, window[np.newaxis, :]], axis=1
                    )
                    output, state = self._session.run(
                        None, {"input": model_input, "state": state, "sr": sample_rate}
                    )
                    context = model_input[:, -_CONTEXT_SAMPLES:]
                    probabilities.append(float(output[0][0]))

        return probabilities
