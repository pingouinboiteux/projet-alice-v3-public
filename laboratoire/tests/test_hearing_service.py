from __future__ import annotations

import io
import wave

import numpy as np
import pytest

from alice.hearing.client import wav_bytes
from alice.hearing.service import decode_wav


def test_wav_contract_round_trip():
    audio = np.linspace(-0.5, 0.5, 16000, dtype=np.float32)
    decoded = decode_wav(wav_bytes(audio))
    assert decoded.shape == audio.shape
    assert np.max(np.abs(decoded - audio)) < 1e-4


def test_wrong_sample_rate_is_rejected():
    stream = io.BytesIO()
    with wave.open(stream, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(np.zeros(2400, dtype="<i2").tobytes())
    with pytest.raises(ValueError, match="16000"):
        decode_wav(stream.getvalue())
