"""Client local borne du pont vocal Discord."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass

from remote_contracts import DiscordUtterance

MAX_EVENT_AUDIO = 16000 * 2 * 30
MAX_PLAYBACK_AUDIO = 24000 * 2 * 30


@dataclass(frozen=True)
class BridgeEvent:
    kind: str
    user_id: str
    human_epoch: int
    utterance: DiscordUtterance | None = None


class DiscordBridgeClient:
    def __init__(self, base_url: str, local_key: str, *, timeout: float = 2.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.local_key = local_key
        self.timeout = timeout

    def _request(self, route: str, *, data: bytes | None = None, method: str = "GET"):
        return urllib.request.Request(
            self.base_url + route,
            data=data,
            headers={"X-Alice-Key": self.local_key},
            method=method,
        )

    def next(self) -> BridgeEvent | None:
        with urllib.request.urlopen(
            self._request("/next"), timeout=self.timeout
        ) as response:
            if response.status == 204:
                return None
            encoded = response.headers.get("X-Alice-Discord-Event", "")
            padding = "=" * (-len(encoded) % 4)
            metadata = json.loads(
                base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
            )
            if not isinstance(metadata, dict):
                raise ValueError("evenement Discord invalide")
            kind = metadata.get("type")
            if kind in {"speech_start", "speech_stop"}:
                if set(metadata) != {"type", "user_id", "human_epoch"}:
                    raise ValueError("evenement de parole Discord invalide")
                user_id = metadata["user_id"]
                human_epoch = metadata["human_epoch"]
                if (
                    not isinstance(user_id, str)
                    or not user_id.isdecimal()
                    or isinstance(human_epoch, bool)
                    or not isinstance(human_epoch, int)
                    or human_epoch < 0
                ):
                    raise ValueError("auteur Discord invalide")
                if response.read(1):
                    raise ValueError("evenement Discord inattendu")
                return BridgeEvent(kind, user_id, human_epoch)
            if kind != "utterance":
                raise ValueError("type d'evenement Discord inconnu")
            body = response.read(MAX_EVENT_AUDIO + 1)
            if len(body) > MAX_EVENT_AUDIO:
                raise ValueError("audio Discord trop grand")
            utterance_metadata = dict(metadata)
            utterance_metadata.pop("type")
            human_epoch = utterance_metadata.pop("human_epoch", None)
            if (
                isinstance(human_epoch, bool)
                or not isinstance(human_epoch, int)
                or human_epoch < 0
            ):
                raise ValueError("generation de parole Discord invalide")
            utterance = DiscordUtterance.parse(utterance_metadata, body)
            return BridgeEvent(kind, utterance.speaker.user_id, human_epoch, utterance)

    def play(self, pcm_s16le: bytes, expected_human_epoch: int) -> bool:
        if not pcm_s16le or len(pcm_s16le) > MAX_PLAYBACK_AUDIO:
            raise ValueError("voix Discord invalide")
        if (
            isinstance(expected_human_epoch, bool)
            or not isinstance(expected_human_epoch, int)
            or expected_human_epoch < 0
        ):
            raise ValueError("generation humaine Discord invalide")
        try:
            request = self._request("/play", data=pcm_s16le, method="POST")
            request.add_header("X-Alice-Human-Epoch", str(expected_human_epoch))
            with urllib.request.urlopen(
                request,
                timeout=max(self.timeout, 10.0),
            ) as response:
                return response.status == 202
        except urllib.error.HTTPError as error:
            if error.code == 409:
                return False
            raise

    def reserve_reply(self, expected_human_epoch: int) -> bool:
        if (
            isinstance(expected_human_epoch, bool)
            or not isinstance(expected_human_epoch, int)
            or expected_human_epoch < 0
        ):
            raise ValueError("generation humaine Discord invalide")
        try:
            request = self._request("/reply/reserve", data=b"", method="POST")
            request.add_header("X-Alice-Human-Epoch", str(expected_human_epoch))
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status == 202
        except urllib.error.HTTPError as error:
            if error.code == 409:
                return False
            raise

    def release_reply(self, expected_human_epoch: int) -> None:
        if (
            isinstance(expected_human_epoch, bool)
            or not isinstance(expected_human_epoch, int)
            or expected_human_epoch < 0
        ):
            raise ValueError("generation humaine Discord invalide")
        request = self._request("/reply/release", data=b"", method="POST")
        request.add_header("X-Alice-Human-Epoch", str(expected_human_epoch))
        with urllib.request.urlopen(request, timeout=self.timeout):
            return

    def play_part(
        self,
        pcm_s16le: bytes,
        expected_human_epoch: int,
        *,
        reply_id: str,
        part_index: int,
        final: bool,
    ) -> bool:
        if not pcm_s16le or len(pcm_s16le) > MAX_PLAYBACK_AUDIO:
            raise ValueError("bloc vocal Discord invalide")
        if (
            isinstance(expected_human_epoch, bool)
            or not isinstance(expected_human_epoch, int)
            or expected_human_epoch < 0
        ):
            raise ValueError("generation humaine Discord invalide")
        if len(reply_id) != 32 or any(
            character not in "0123456789abcdef" for character in reply_id
        ):
            raise ValueError("reponse Discord invalide")
        if (
            isinstance(part_index, bool)
            or not isinstance(part_index, int)
            or part_index < 0
        ):
            raise ValueError("position vocale Discord invalide")
        try:
            request = self._request("/play-part", data=pcm_s16le, method="POST")
            request.add_header("X-Alice-Human-Epoch", str(expected_human_epoch))
            request.add_header("X-Alice-Reply-Id", reply_id)
            request.add_header("X-Alice-Part-Index", str(part_index))
            request.add_header("X-Alice-Final-Part", "1" if final else "0")
            with urllib.request.urlopen(
                request,
                timeout=max(self.timeout, 10.0),
            ) as response:
                return response.status == 202
        except urllib.error.HTTPError as error:
            if error.code == 409:
                return False
            raise

    def stop(self) -> None:
        with urllib.request.urlopen(
            self._request("/stop", data=b"", method="POST"), timeout=self.timeout
        ):
            return

    def health(self) -> dict[str, object]:
        with urllib.request.urlopen(
            self.base_url + "/health", timeout=self.timeout
        ) as response:
            value = json.loads(response.read(64 * 1024).decode("utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("signature") != "alice-discord-voice"
        ):
            raise RuntimeError("pont Discord invalide")
        return value


