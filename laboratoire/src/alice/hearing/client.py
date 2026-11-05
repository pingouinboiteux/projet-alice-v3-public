"""Client du service de transcription."""

from __future__ import annotations

import io
import json
import urllib.request
import wave

import numpy as np


def wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
    values = np.asarray(audio)
    if values.ndim != 1:
        raise ValueError("audio mono requis")
    if values.dtype != np.int16:
        values = np.clip(values.astype(np.float32), -1.0, 1.0)
        values = (values * 32767).astype("<i2")
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        output.writeframes(values.astype("<i2", copy=False).tobytes())
    return stream.getvalue()


class HearingClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.url = base_url.rstrip("/") + "/transcribe"
        self.timeout = timeout

    def transcribe(self, audio: np.ndarray) -> str:
        request = urllib.request.Request(
            self.url,
            data=wav_bytes(audio),
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            value = json.loads(response.read(1024 * 1024).decode("utf-8"))
        text = value.get("text")
        if not isinstance(text, str):
            raise RuntimeError("transcription absente")
        return text.strip()
