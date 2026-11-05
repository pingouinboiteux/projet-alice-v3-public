"""Lecture progressive du flux PCM produit par la voix."""

from __future__ import annotations

import json
import struct
import urllib.request
from collections.abc import Callable, Iterator

import numpy as np

from alice.voice.guards import validate_audio_length
from alice.voice.text import chunks

MAX_BLOCK = 24000 * 2 * 120


def _read_exact(stream, size: int) -> bytes | None:
    parts: list[bytes] = []
    remaining = size
    while remaining:
        part = stream.read(remaining)
        if not part:
            return None
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


class VoiceClient:
    def __init__(self, base_url: str, timeout: float = 300.0) -> None:
        self.url = base_url.rstrip("/") + "/speak"
        self.timeout = timeout

    def blocks(self, text: str) -> Iterator[bytes]:
        body = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        response = urllib.request.urlopen(request, timeout=self.timeout)
        parts = chunks(text)
        index = 0
        try:
            while True:
                header = _read_exact(response, 4)
                if header is None:
                    raise RuntimeError("flux de voix termine sans marque de fin")
                size = struct.unpack(">I", header)[0]
                if size == 0:
                    if index != len(parts):
                        raise RuntimeError("flux vocal incomplet")
                    return
                if size > MAX_BLOCK or size % 2 or index >= len(parts):
                    raise RuntimeError("bloc de voix trop grand")
                validate_audio_length(parts[index], size // 2, 24000)
                block = _read_exact(response, size)
                if block is None:
                    raise RuntimeError("bloc de voix tronque")
                yield block
                index += 1
        finally:
            response.close()

    def play(
        self,
        text: str,
        *,
        on_start: Callable[[], None] | None = None,
        on_stop: Callable[[], None] | None = None,
        on_level: Callable[[float], None] | None = None,
        on_part: Callable[[str], None] | None = None,
    ) -> float:
        import sounddevice as sd

        started = False
        duration = 0.0
        level = 0.0
        parts = chunks(text)
        received_blocks = 0
        try:
            with sd.OutputStream(
                samplerate=24000, channels=1, dtype="int16", latency="high"
            ) as output:
                for index, raw in enumerate(self.blocks(text)):
                    received_blocks += 1
                    if not started:
                        started = True
                        if on_start:
                            on_start()
                    if on_part and index < len(parts):
                        on_part(parts[index])
                    pcm = np.frombuffer(raw, dtype="<i2")
                    for offset in range(0, len(pcm), 1200):
                        piece = pcm[offset : offset + 1200]
                        output.write(piece)
                        duration += len(piece) / 24000
                        if on_level and len(piece):
                            normalized = piece.astype(np.float32) / 32768.0
                            measured = min(
                                1.0, float(np.sqrt(np.mean(normalized**2))) * 6.0
                            )
                            level = 0.65 * level + 0.35 * measured
                            on_level(level)
            if received_blocks != len(parts):
                raise RuntimeError(
                    f"flux vocal incomplet : {received_blocks} blocs recus, "
                    f"{len(parts)} attendus"
                )
            return duration
        finally:
            if on_level:
                on_level(0.0)
            if started and on_stop:
                on_stop()
