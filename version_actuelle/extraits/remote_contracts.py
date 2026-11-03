"""Contrats bornes entre le pont Discord et Alice."""

from __future__ import annotations

import re
from dataclasses import dataclass

_SNOWFLAKE = re.compile(r"[1-9][0-9]{5,24}")
_UTTERANCE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{7,95}")


def _clean_name(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("nom Discord invalide")
    clean = " ".join(value.split())
    if not 1 <= len(clean) <= 80 or any(ord(char) < 32 for char in clean):
        raise ValueError("nom Discord invalide")
    return clean


@dataclass(frozen=True)
class DiscordSpeaker:
    """Identite Discord certaine; le nom n'est qu'une etiquette affichable."""

    user_id: str
    display_name: str
    bot: bool

    @classmethod
    def parse(cls, value: object) -> DiscordSpeaker:
        if not isinstance(value, dict) or set(value) != {
            "user_id",
            "display_name",
            "bot",
        }:
            raise ValueError("identite Discord invalide")
        user_id = value["user_id"]
        if not isinstance(user_id, str) or _SNOWFLAKE.fullmatch(user_id) is None:
            raise ValueError("identifiant Discord invalide")
        if not isinstance(value["bot"], bool):
            raise ValueError("indicateur de bot invalide")
        return cls(user_id, _clean_name(value["display_name"]), value["bot"])


@dataclass(frozen=True)
class DiscordUtterance:
    """Une parole terminee, deja associee a son auteur par Discord."""

    utterance_id: str
    speaker: DiscordSpeaker
    pcm_s16le: bytes
    sample_rate: int = 16000

    @classmethod
    def parse(cls, metadata: object, pcm_s16le: bytes) -> DiscordUtterance:
        if not isinstance(metadata, dict) or set(metadata) != {
            "utterance_id",
            "speaker",
            "sample_rate",
        }:
            raise ValueError("parole Discord invalide")
        utterance_id = metadata["utterance_id"]
        if (
            not isinstance(utterance_id, str)
            or _UTTERANCE_ID.fullmatch(utterance_id) is None
        ):
            raise ValueError("identifiant de parole invalide")
        if metadata["sample_rate"] != 16000:
            raise ValueError("frequence Discord invalide")
        if not isinstance(pcm_s16le, bytes) or len(pcm_s16le) % 2:
            raise ValueError("audio Discord invalide")
        duration = len(pcm_s16le) / (2 * 16000)
        if not 0.5 <= duration <= 30.0:
            raise ValueError("duree Discord invalide")
        return cls(
            utterance_id,
            DiscordSpeaker.parse(metadata["speaker"]),
            pcm_s16le,
        )

    @property
    def duration_seconds(self) -> float:
        return len(self.pcm_s16le) / (2 * self.sample_rate)
