"""Detection de fin de tour a partir de l'intonation."""

from __future__ import annotations

import numpy as np

from alice.settings import load_settings

SAMPLE_RATE = 16000
FFT_SIZE = 400
HOP = 160
SAMPLES = 8 * SAMPLE_RATE


def log_mel(audio: np.ndarray, filters_path=None) -> np.ndarray:
    settings = load_settings()
    path = filters_path or settings.path("turn_mel_filters")
    values = np.asarray(audio)[-SAMPLES:].astype(np.float32)
    if not values.size:
        raise ValueError("audio vide")
    values = (values - values.mean()) / np.sqrt(values.var() + 1e-7)
    if len(values) < SAMPLES:
        values = np.concatenate(
            [values, np.zeros(SAMPLES - len(values), dtype=np.float32)]
        )
    window = np.hanning(FFT_SIZE + 1)[:-1].astype(np.float32)
    values = np.pad(values, FFT_SIZE // 2, mode="reflect")
    frame_count = 1 + (len(values) - FFT_SIZE) // HOP
    frames = np.lib.stride_tricks.as_strided(
        values,
        shape=(frame_count, FFT_SIZE),
        strides=(values.strides[0] * HOP, values.strides[0]),
    ).copy()
    spectrum = np.abs(np.fft.rfft(frames * window, axis=1)) ** 2
    spectrum = spectrum[:-1]
    filters = np.load(path)["mel_80"].astype(np.float32)
    mel = filters @ spectrum.T
    mel = np.log10(np.maximum(mel, 1e-10))
    mel = np.maximum(mel, mel.max() - 8.0)
    return ((mel + 4.0) / 4.0).astype(np.float32)


class TurnDetector:
    def __init__(self, model_path=None, filters_path=None) -> None:
        import onnxruntime as ort

        settings = load_settings()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.filters_path = filters_path or settings.path("turn_mel_filters")
        self.session = ort.InferenceSession(
            str(model_path or settings.path("turn_detector")),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

    def probability(self, audio: np.ndarray) -> float:
        values = np.asarray(audio)
        if values.dtype == np.int16:
            values = values.astype(np.float32) / 32768.0
        features = log_mel(values, self.filters_path)[np.newaxis, :, :]
        output = self.session.run(None, {"input_features": features})[0]
        probability = float(output.reshape(-1)[0])
        if not 0.0 <= probability <= 1.0:
            probability = 1.0 / (1.0 + np.exp(-probability))
        return max(0.0, min(1.0, probability))
