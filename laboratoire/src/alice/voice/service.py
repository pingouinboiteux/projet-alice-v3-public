"""Service Chatterbox optimise pour une carte AMD reservee."""

from __future__ import annotations

import io
import json
import os
import re
import struct
import sys
import threading
import time
import traceback
import unicodedata
import urllib.request
import warnings
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from alice.hardware import alice_pci_bus
from alice.logging import EventLog
from alice.paths import inside
from alice.settings import load_settings
from alice.voice.guards import (
    UnsafeSynthesisError,
    require_complete_inference,
    validate_audio_length,
)
from alice.voice.text import chunks

os.environ.setdefault("MIOPEN_LOG_LEVEL", "1")
os.environ.setdefault("MIOPEN_FIND_MODE", "FAST")
os.environ.setdefault("ROCM_SDK_TARGET_FAMILY", "custom")
MIOPEN_CACHE = inside("cache/miopen")
MIOPEN_CACHE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MIOPEN_USER_DB_PATH", str(MIOPEN_CACHE))
os.environ.setdefault("MIOPEN_CUSTOM_CACHE_DIR", str(MIOPEN_CACHE))


SIGNATURE = "alice-voice"
MODEL = None
TORCH = None
NUMPY = None
SAMPLE_RATE = 24000
GENERATION_LOCK = threading.Lock()
REQUEST_ACTIVITY_LOCK = threading.Lock()
ACTIVE_REQUESTS = 0
LAST_SYNTHESIS = 0.0
LAST_REQUEST = 0.0
THREAD_WARMED = False
LOG = EventLog("voice")
MAX_VERIFICATION_ATTEMPTS = 3


def pronunciation_text(text: str) -> str:
    """Corrige uniquement la graphie envoyee au moteur vocal."""
    text = re.sub(r"\bAlice\b", "Alisse", text, flags=re.IGNORECASE)
    return re.sub(
        r"\b([NZ])oé\b",
        lambda match: f"{match.group(1)}ohé",
        text,
        flags=re.IGNORECASE,
    )


def _request_started() -> None:
    global ACTIVE_REQUESTS
    with REQUEST_ACTIVITY_LOCK:
        ACTIVE_REQUESTS += 1


def _request_finished() -> None:
    global ACTIVE_REQUESTS
    with REQUEST_ACTIVITY_LOCK:
        if ACTIVE_REQUESTS <= 0:
            raise RuntimeError("compteur de requetes vocales incoherent")
        ACTIVE_REQUESTS -= 1


def _request_busy() -> bool:
    with REQUEST_ACTIVITY_LOCK:
        return ACTIVE_REQUESTS > 0


def synthesize_unlocked(text: str):
    global LAST_SYNTHESIS
    settings = load_settings().section("voice")
    LAST_SYNTHESIS = time.time()
    started = time.perf_counter()
    with TORCH.inference_mode():
        wave = MODEL.generate(
            pronunciation_text(text),
            language_id="fr",
            exaggeration=settings["exaggeration"],
            temperature=settings["temperature"],
            cfg_weight=settings["guidance"],
        )
    values = wave.squeeze().detach().cpu().numpy().astype("float32")
    validate_audio_length(text, values.size, SAMPLE_RATE)
    if values.ndim != 1 or not NUMPY.isfinite(values).all():
        raise UnsafeSynthesisError("echantillons vocaux invalides")
    peak = float(NUMPY.abs(values).max())
    if peak > 0:
        values = values / peak * 0.89
    pcm = NUMPY.clip(values * 32767, -32768, 32767).astype("<i2")
    elapsed = time.perf_counter() - started
    duration = len(pcm) / SAMPLE_RATE
    LOG.write(
        "chunk_synthesized",
        characters=len(text),
        audio_seconds=round(duration, 3),
        elapsed_seconds=round(elapsed, 3),
        realtime_factor=round(elapsed / max(duration, 0.001), 3),
    )
    return pcm


def synthesize(text: str):
    with GENERATION_LOCK:
        return synthesize_unlocked(text)


def _verification_text(text: str) -> str:
    value = unicodedata.normalize("NFKD", text.casefold())
    value = "".join(
        character for character in value if not unicodedata.combining(character)
    )
    value = " ".join(re.sub(r"[^a-z0-9]+", " ", value).split())
    value = re.sub(r"\bmaya\b", "maia", value)
    numbers = {
        "0": "zero",
        "1": "un",
        "2": "deux",
        "3": "trois",
        "4": "quatre",
        "5": "cinq",
        "6": "six",
        "7": "sept",
        "8": "huit",
        "9": "neuf",
        "10": "dix",
        "11": "onze",
        "12": "douze",
        "13": "treize",
        "14": "quatorze",
        "15": "quinze",
        "16": "seize",
        "17": "dix sept",
        "18": "dix huit",
        "19": "dix neuf",
        "20": "vingt",
        "21": "vingt et un",
        "22": "vingt deux",
        "23": "vingt trois",
        "24": "vingt quatre",
        "25": "vingt cinq",
        "26": "vingt six",
        "27": "vingt sept",
        "28": "vingt huit",
        "29": "vingt neuf",
        "30": "trente",
    }
    return re.sub(
        r"\b(?:[0-9]|[12][0-9]|30)\b", lambda match: numbers[match.group()], value
    )


def _word_distance(left: str, right: str) -> int:
    source = _verification_text(left).split()
    candidate = _verification_text(right).split()
    previous = list(range(len(candidate) + 1))
    for index, word in enumerate(source, 1):
        current = [index]
        for other, value in enumerate(candidate, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[other] + 1,
                    previous[other - 1] + (word != value),
                )
            )
        previous = current
    return previous[-1]


def _verification_wav(pcm) -> bytes:
    from scipy.signal import resample_poly

    converted = resample_poly(pcm.astype("float32"), 2, 3)
    converted = NUMPY.clip(NUMPY.rint(converted), -32768, 32767).astype("<i2")
    target = io.BytesIO()
    with wave.open(target, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(converted.tobytes())
    return target.getvalue()


def _verification_transcript(pcm) -> str:
    network = load_settings().section("network")
    request = urllib.request.Request(
        f"http://{network['host']}:{network['hearing_port']}/transcribe",
        data=_verification_wav(pcm),
        headers={"Content-Type": "audio/wav"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read(64 * 1024).decode("utf-8"))
    text = payload.get("text") if isinstance(payload, dict) else None
    if not isinstance(text, str):
        raise ValueError("transcription de verification absente")
    return text.strip()


def synthesize_verified(text: str):
    """Keep the closest of at most three in-memory pronunciations."""
    candidates = []
    for attempt in range(1, MAX_VERIFICATION_ATTEMPTS + 1):
        pcm = synthesize(text)
        try:
            transcript = _verification_transcript(pcm)
        except Exception as exc:
            LOG.write(
                "pronunciation_verification_unavailable", error=type(exc).__name__
            )
            return pcm
        score = _word_distance(text, transcript)
        candidates.append((score, attempt, pcm))
        if score == 0:
            LOG.write(
                "pronunciation_selected", attempts=attempt, exact=True, distance=0
            )
            return pcm
    score, attempt, pcm = min(candidates, key=lambda item: (item[0], item[1]))
    LOG.write(
        "pronunciation_selected",
        attempts=len(candidates),
        selected_attempt=attempt,
        exact=False,
        distance=score,
    )
    return pcm


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "AliceVoice/1"

    def log_message(self, *_args) -> None:
        return

    def _empty(self, code: int) -> None:
        self.send_response(code)
        self.send_header("Content-Length", "0")
        self.end_headers()

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
        self._json(
            200,
            {
                "signature": SIGNATURE,
                "ready": MODEL is not None and THREAD_WARMED,
                "busy": _request_busy(),
                "generation_busy": GENERATION_LOCK.locked(),
            },
        )

    def do_POST(self) -> None:
        if self.path != "/speak":
            self._empty(404)
            return
        if MODEL is None:
            self._empty(503)
            return
        _request_started()
        try:
            self._speak()
        finally:
            _request_finished()

    def _speak(self) -> None:
        global LAST_REQUEST
        LAST_REQUEST = time.time()
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 2 <= length <= 256 * 1024:
                raise ValueError("taille de requete invalide")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            text = payload.get("text") if isinstance(payload, dict) else None
            if not isinstance(text, str) or not text.strip():
                raise ValueError("texte absent")
            parts = chunks(text)
            first = synthesize_verified(parts[0])
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            self._empty(400)
            return
        except Exception as exc:
            LOG.write(
                "synthesis_failed", error=type(exc).__name__, detail=str(exc)[:500]
            )
            self._empty(500)
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for index, part in enumerate(parts):
                pcm = first if index == 0 else synthesize_verified(part)
                raw = pcm.tobytes()
                framed = struct.pack(">I", len(raw)) + raw
                self.wfile.write(f"{len(framed):X}\r\n".encode("ascii"))
                self.wfile.write(framed + b"\r\n")
                self.wfile.flush()
            end = struct.pack(">I", 0)
            self.wfile.write(f"{len(end):X}\r\n".encode("ascii") + end + b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except UnsafeSynthesisError:
            LOG.write("synthesis_rejected", reason="unsafe_audio")
            self.close_connection = True
        except Exception:
            LOG.write("client_disconnected")
            self.close_connection = True


def load_on_selected_device(factory, path, device: str):
    """Ignore les anciens numeros CUDA enregistres dans les poids tiers."""
    model = factory.from_local(path, device="cpu", t3_model="v3")
    for component in (model.t3, model.s3gen, model.ve):
        component.to(device)
    model.device = device
    if model.conds is not None:
        model.conds = model.conds.to(device)
    return model


def _load_model(device: str) -> None:
    global MODEL
    source = inside("vendor")
    if not inside("vendor/chatterbox").is_dir():
        raise FileNotFoundError("le moteur source de la voix est absent")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    warnings.filterwarnings(
        "ignore",
        message="pkg_resources is deprecated as an API.*",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message="`LoRACompatibleLinear` is deprecated.*",
        category=FutureWarning,
    )
    warnings.filterwarnings(
        "ignore", message="`torch.backends.cuda.sdp_kernel.*", category=FutureWarning
    )
    warnings.filterwarnings(
        "ignore", message="Using AOTriton backend.*", category=UserWarning
    )
    import librosa
    from chatterbox.models.s3gen import S3Gen, flow_matching
    from chatterbox.models.t3 import t3
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from safetensors.torch import load_file

    settings = load_settings()
    voice = settings.section("voice")
    reference = settings.path("voice_reference")
    wave_model = settings.path("voice_wave_model")
    if not reference.is_file() or not wave_model.is_file():
        raise FileNotFoundError("ressources de voix incompletes")

    MODEL = load_on_selected_device(
        ChatterboxMultilingualTTS, settings.path("voice_base"), device
    )
    MODEL.t3.inference = require_complete_inference(
        MODEL.t3.inference, MODEL.t3.hp.stop_speech_token
    )
    if MODEL.sr != voice["sample_rate"]:
        raise RuntimeError(f"echantillonnage inattendu : {MODEL.sr}")
    MODEL.prepare_conditionals(str(reference), exaggeration=voice["exaggeration"])

    flow_matching.tqdm = lambda iterable, **_options: iterable
    flow_matching.print = lambda *_args, **_options: None
    t3.tqdm = lambda iterable, **_options: iterable
    stage = S3Gen(meanflow=True)
    stage.load_state_dict(load_file(str(wave_model)), strict=True)
    stage.to(device).eval()
    reference_wave, _ = librosa.load(str(reference), sr=SAMPLE_RATE)
    MODEL.conds.gen = stage.embed_ref(
        reference_wave[: MODEL.DEC_COND_LEN], SAMPLE_RATE, device=device
    )
    previous = MODEL.s3gen
    MODEL.s3gen = stage
    del previous
    TORCH.cuda.empty_cache()


def _warm_direct() -> None:
    for text in (
        "Oui.",
        "Je suis la.",
        "Bien. Maintenant, raconte.",
        "Cette phrase prepare une reponse de longueur moyenne.",
        "Je prends le temps de preparer une phrase plus longue, avec une respiration naturelle, afin que la premiere conversation soit aussi fluide que les suivantes.",
    ):
        synthesize(text)


def _read_exact(stream, size: int) -> bytes:
    parts: list[bytes] = []
    remaining = size
    while remaining:
        part = stream.read(remaining)
        if not part:
            raise EOFError("flux audio tronque")
        parts.append(part)
        remaining -= len(part)
    return b"".join(parts)


def _warm_http(port: int) -> None:
    body = json.dumps({"text": "Oui, je suis la."}).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/speak",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=180) as response:
        while True:
            size = struct.unpack(">I", _read_exact(response, 4))[0]
            if size == 0:
                return
            _read_exact(response, size)


def _keep_warm() -> None:
    threshold = float(load_settings().section("voice")["keep_warm_after_seconds"])
    while True:
        time.sleep(1.5)
        try:
            now = time.time()
            if now - LAST_SYNTHESIS < threshold or now - LAST_REQUEST < 6.0:
                continue
            if not GENERATION_LOCK.acquire(blocking=False):
                continue
            try:
                synthesize_unlocked("Oui.")
            finally:
                GENERATION_LOCK.release()
        except Exception as exc:
            LOG.write("keep_warm_failed", error=type(exc).__name__)
            time.sleep(30)


def main() -> None:
    global TORCH, NUMPY, THREAD_WARMED
    import numpy as np
    import torch

    TORCH = torch
    NUMPY = np
    if not torch.cuda.is_available():
        raise RuntimeError("aucune carte ROCm disponible")
    target_bus = alice_pci_bus()
    matching = [
        index
        for index in range(torch.cuda.device_count())
        if int(getattr(torch.cuda.get_device_properties(index), "pci_bus_id", -1))
        == target_bus
    ]
    if len(matching) != 1:
        raise RuntimeError("la carte de voix n'est pas identifiable par son bus PCI")
    index = matching[0]
    torch.cuda.set_device(index)
    device = f"cuda:{index}"
    started = time.perf_counter()
    _load_model(device)
    _warm_direct()

    network = load_settings().section("network")
    server = ThreadingHTTPServer((network["host"], network["voice_port"]), Handler)
    thread = threading.Thread(
        target=server.serve_forever, name="voice-http", daemon=True
    )
    thread.start()
    _warm_http(network["voice_port"])
    THREAD_WARMED = True
    threading.Thread(target=_keep_warm, name="voice-keep-warm", daemon=True).start()
    properties = torch.cuda.get_device_properties(index)
    LOG.write(
        "ready",
        port=network["voice_port"],
        device=device,
        pci_bus=target_bus,
        gpu=properties.name,
        load_seconds=round(time.perf_counter() - started, 3),
    )
    try:
        thread.join()
    finally:
        server.shutdown()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.stderr.flush()
        os._exit(1)
