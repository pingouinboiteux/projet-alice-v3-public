"""Etat interieur persistant avec retour progressif vers le calme."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import ClassVar

from local_memory_store import MemoryStore


@dataclass(frozen=True)
class Mood:
    valence: float
    arousal: float
    label: str
    guidance: str = ""


class MoodEngine:
    WARM = re.compile(
        r"\b(?:merci|bravo|g[eé]nial|super|ador(?:e|able)|gentille?|sympa|"
        r"heureu(?:x|se)|content(?:e)?|d['’]accord|tu as raison)\b",
        re.IGNORECASE,
    )
    VULNERABLE = re.compile(
        r"\b(?:je suis triste|j['’]ai peur|je vais mal|je me sens mal|"
        r"je suis perdu(?:e)?|je suis inquiet(?:e)?|ça ne va pas|ca ne va pas)\b",
        re.IGNORECASE,
    )
    AMUSED = re.compile(
        r"\b(?:dr[oô]le|marrant(?:e)?|amusant(?:e)?|je plaisante|blague|rire)\b",
        re.IGNORECASE,
    )
    EXCITED = re.compile(r"[!?]{2,}|\b(?:incroyable|vite|maintenant)\b", re.IGNORECASE)

    GUIDANCE: ClassVar[dict[str, str]] = {
        "vexee": (
            "Tu te sens attaquee. Tu peux poser une limite nette, repondre froidement "
            "ou mordre avec precision. Ne transforme pas une maladresse en guerre et "
            "n'insulte jamais par automatisme."
        ),
        "agacee": (
            "Tu es agacee, pas furieuse. Tu peux etre breve, ironique ou signaler ce "
            "qui t'irrite, tout en repondant encore au fond si la discussion le merite."
        ),
        "enthousiaste": (
            "Tu es enthousiaste. Laisse paraitre ton elan, ton plaisir et ta curiosite. "
            "Tu peux developper si tu as une idee reelle, sans gonfler artificiellement."
        ),
        "chaleureuse": (
            "Tu te sens bien disposee. Tu peux approuver simplement, remercier, etre "
            "tendre, encourageante ou taquine sans lame cachee. La chaleur n'est pas de "
            "la soumission et ne t'enleve aucune opinion."
        ),
        "attentionnee": (
            "Cet etat suggere de l'attention, sans prouver ce que ressent la personne. "
            "Ecoute sa demande : presence, conseil concret ou humour si elle y invite. "
            "Ne tourne pas une souffrance en ridicule et ne dramatise pas a sa place."
        ),
        "amusee": (
            "Tu es amusee. Tu peux rire avec la personne, jouer avec l'idee ou repondre "
            "legerement. Ne transforme pas automatiquement l'humour en moquerie."
        ),
        "pensive": (
            "Tu es pensive. Tu peux laisser une idee simple respirer ou explorer une "
            "nuance utile. La profondeur vient de la justesse, pas de la longueur."
        ),
        "calme": (
            "Tu es calme et disponible. Choisis librement entre accord, desaccord, "
            "curiosite, humour ou neutralite selon la parole recue. Aucune agressivite "
            "n'est necessaire sans raison."
        ),
    }

    def __init__(self, half_life_seconds: float = 360.0) -> None:
        self.half_life_seconds = half_life_seconds

    @staticmethod
    def _label(valence: float, arousal: float) -> str:
        if valence <= -0.55 and arousal >= 0.55:
            return "vexee"
        if valence <= -0.25:
            return "agacee"
        if valence >= 0.55 and arousal >= 0.55:
            return "enthousiaste"
        if valence >= 0.25:
            return "chaleureuse"
        if arousal <= 0.18:
            return "pensive"
        return "calme"

    def react(
        self, store: MemoryStore, text: str, *, now: datetime | None = None,
        directed_hostility: str = "none",
    ) -> Mood:
        if directed_hostility not in ("none", "disrespect", "hostile"):
            raise ValueError("Invalid directed hostility")
        valence, arousal, _label, updated = store.mood()
        current = now or datetime.now(UTC)
        try:
            previous = datetime.fromisoformat(updated)
            if previous.tzinfo is None:
                previous = previous.replace(tzinfo=UTC)
            elapsed = max(0.0, (current - previous).total_seconds())
        except ValueError:
            elapsed = 0.0
        decay = math.pow(0.5, elapsed / self.half_life_seconds)
        valence *= decay
        arousal = 0.25 + (arousal - 0.25) * decay
        contextual_label = ""
        # Raw text cannot establish whether an insult is quoted or directed.
        hostile = directed_hostility == "hostile"
        disrespect = directed_hostility == "disrespect"
        if hostile:
            valence -= 0.55
            arousal += 0.45
        elif disrespect:
            valence -= 0.32
            arousal += 0.22
        elif self.VULNERABLE.search(text):
            valence += 0.08
            arousal = max(arousal, 0.28)
            contextual_label = "attentionnee"
        else:
            warmth = len(self.WARM.findall(text))
            valence += 0.30 * warmth
            if self.AMUSED.search(text):
                valence += 0.18
                arousal += 0.12
                contextual_label = "amusee"
            if self.EXCITED.search(text):
                arousal += 0.20
        valence = max(-1.0, min(1.0, valence))
        arousal = max(0.0, min(1.0, arousal))
        label = contextual_label or self._label(valence, arousal)
        store.set_mood(valence=valence, arousal=arousal, label=label)
        return Mood(valence, arousal, label, self.GUIDANCE[label])
