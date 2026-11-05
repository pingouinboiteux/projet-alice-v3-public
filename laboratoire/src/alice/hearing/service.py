"""Service local de transcription francaise."""

from __future__ import annotations

import io
import json
import os
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np

from alice.logging import EventLog
from alice.settings import load_settings

SIGNATURE = "alice-hearing"
LANGUAGE = "fr"
MODEL = None
MODEL_LOCK = threading.Lock()
LOG = EventLog("hearing")


def decode_wav(raw: bytes, expected_rate: int = 16000) -> np.ndarray:
    try:
        with wave.open(io.BytesIO(raw), "rb") as stream:
            if stream.getnchannels() != 1:
                raise ValueError("audio mono requis")
            if stream.getsampwidth() != 2:
                raise ValueError("audio PCM 16 bits requis")
            if stream.getframerate() != expected_rate:
                raise ValueError(f"audio {expected_rate} Hz requis")
            frames = stream.getnframes()
            if not 1 <= frames <= expected_rate * 120:
                raise ValueError("duree audio invalide")
            data = stream.readframes(frames)
    except (wave.Error, EOFError) as exc:
        raise ValueError("fichier WAV invalide") from exc
    return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0


class Handler(BaseHTTPRequestHandler):
    server_version = "AliceHearing/1"

    def log_message(self, *_args) -> None:
        return

    def _json(self, code: int, value: dict) -> None:
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path.rstrip("/") not in {"", "/health"}:
            self._json(404, {"error": "route inconnue"})
            return
        self._json(200, {"signature": SIGNATURE, "ready": MODEL is not None})

    def do_POST(self) -> None:
        if self.path != "/transcribe":
            self._json(404, {"error": "route inconnue"})
            return
        if MODEL is None:
            self._json(503, {"error": "oreille en chargement"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 44 <= length <= 4 * 1024 * 1024:
                raise ValueError("taille audio invalide")
            audio = decode_wav(self.rfile.read(length))
            started = time.perf_counter()
            with MODEL_LOCK:
                text = MODEL.recognize(
                    audio,
                    sample_rate=16000,
                    language=LANGUAGE,
                    target_language=LANGUAGE,
                ).strip()
            elapsed = time.perf_counter() - started
            LOG.write(
                "transcribed",
                audio_seconds=round(len(audio) / 16000, 3),
                elapsed_seconds=round(elapsed, 3),
                characters=len(text),
            )
            self._json(200, {"text": text, "elapsed_seconds": round(elapsed, 3)})
        except ValueError as exc:
            self._json(400, {"error": str(exc)})
        except Exception as exc:
            LOG.write(
                "transcription_failed", error=type(exc).__name__, detail=str(exc)[:500]
            )
            self._json(500, {"error": "transcription impossible"})


def load_model():
    import onnx_asr
    import onnxruntime as ort

    settings = load_settings()
    architecture = settings.value("models", "hearing_architecture", str)
    options = ort.SessionOptions()
    options.intra_op_num_threads = settings.value("hardware", "hearing_threads", int)
    options.inter_op_num_threads = 1
    # Keep the same FP32 model/kernels without retaining the CPU arena's reserve.
    options.enable_cpu_mem_arena = False
    providers: list = ["CPUExecutionProvider"]
    if os.environ.get("ALICE_HEARING_DML", "0") == "1":
        if "DmlExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("DirectML demande mais indisponible")
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        device_id = int(os.environ.get("ALICE_HEARING_DML_DEVICE", "0"))
        providers = [
            ("DmlExecutionProvider", {"device_id": device_id}),
            "CPUExecutionProvider",
        ]
    return onnx_asr.load_model(
        architecture,
        path=str(settings.path("hearing")),
        sess_options=options,
        providers=providers,
    )


def main() -> None:
    global MODEL
    settings = load_settings()
    started = time.perf_counter()
    MODEL = load_model()
    network = settings.section("network")
    server = ThreadingHTTPServer((network["host"], network["hearing_port"]), Handler)
    LOG.write(
        "ready",
        port=network["hearing_port"],
        load_seconds=round(time.perf_counter() - started, 3),
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
