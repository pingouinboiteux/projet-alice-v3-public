"""Extraction conservatrice de faits explicitement affirmes."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from alice.memory.store import Event, Memory, MemoryStore, normalize


@dataclass(frozen=True)
class Candidate:
    statement: str
    kind: str
    evidence_quote: str
    confidence: float
    key: str | None = None


def _clean_value(value: str) -> str:
    value = value.strip(" \t\r\n.,;:!?\"'")
    return " ".join(value.split())


class DeterministicExtractor:
    """Ne retient que les formulations qui portent elles-memes leur preuve."""

    _patterns = (
        (
            re.compile(
                r"\b(?:je m['’]appelle|mon prenom est)\s+([\wÀ-ÿ'-]{2,60})",
                re.IGNORECASE,
            ),
            "identity.name",
            "identity.name",
            lambda value: f"La personne s'appelle {value}.",
        ),
        (
            re.compile(
                r"\b(?:j['’]habite|je vis)\s+(?:a|à|au|aux|en)\s+([^.!?]{2,120})",
                re.IGNORECASE,
            ),
            "identity.location",
            "identity.location",
            lambda value: f"La personne habite a {value}.",
        ),
        (
            re.compile(
                r"\b(?:j['’]adore|j['’]aime|je prefere)\s+([^.!?]{2,160})",
                re.IGNORECASE,
            ),
            "preference.like",
            None,
            lambda value: f"La personne aime {value}.",
        ),
        (
            re.compile(
                r"\b(?:je deteste|je n['’]aime pas)\s+([^.!?]{2,160})", re.IGNORECASE
            ),
            "preference.dislike",
            None,
            lambda value: f"La personne n'aime pas {value}.",
        ),
        (
            re.compile(
                r"\bmon\s+([\wÀ-ÿ'-]{2,40}(?:\s+(?:de|du|des|d['’])?\s*"
                r"[\wÀ-ÿ'-]{2,40}){0,4})\s+est\s+([^.!?]{2,160})",
                re.IGNORECASE,
            ),
            "profile.attribute",
            "profile",
            lambda value: value,
        ),
        (
            re.compile(
                r"\bma\s+([\wÀ-ÿ'-]{2,40}(?:\s+(?:de|du|des|d['’])?\s*"
                r"[\wÀ-ÿ'-]{2,40}){0,4})\s+est\s+([^.!?]{2,160})",
                re.IGNORECASE,
            ),
            "profile.attribute",
            "profile",
            lambda value: value,
        ),
    )
    _explicit = re.compile(
        r"\b(?:souviens[- ]toi|retiens)\s+(?:bien\s+)?que\s+([^.!?]{2,400})",
        re.IGNORECASE,
    )

    def extract(self, text: str) -> list[Candidate]:
        candidates: list[Candidate] = []
        occupied: list[tuple[int, int]] = []
        # Only autonomous assertions are eligible for the fast path. A regex
        # matching inside a question, quotation or hypothesis is not evidence.
        assertions = []
        for sentence in re.finditer(r"[^.!?\n]+(?:[.!?]+|$)", text):
            value = sentence.group(0).strip()
            if "?" in value or re.search(r'["\u00ab\u00bb\u201c\u201d]', value):
                continue
            if re.match(
                r"(?:si\b|suppos|imagin|peut[- ]etre\b|peut[- ]être\b|"
                r"est[- ]ce\b|comment\b|pourquoi\b|quand\b|ou\b|où\b|"
                r"quel\w*\b|qui\b|que\b|tu\b|vous\b|il\b|elle\b|on\b)",
                value,
                re.IGNORECASE,
            ):
                continue
            # Embedded first-person speech about someone else must be left to
            # semantic extraction rather than assigned to this user's profile.
            if not re.match(
                r"(?:(?:pour|dans)\s+[^,]{1,80},\s*)?"
                r"(?:je\b|j['’]|mon\b|ma\b|souviens[- ]toi\b|retiens\b)",
                value,
                re.IGNORECASE,
            ):
                continue
            assertions.append((sentence.start(), sentence.end()))

        def is_assertion(match: re.Match[str]) -> bool:
            for start, end in assertions:
                if start <= match.start() and match.end() <= end:
                    prefix = text[start : match.start()].strip()
                    return not prefix or bool(
                        re.search(
                            r"(?:\b(?:et|mais|puis)\s*|"
                            r"^(?:pour|dans)\s+[^,]{1,80},\s*)$",
                            prefix,
                            re.IGNORECASE,
                        )
                    )
            return False

        for pattern, kind, key_mode, renderer in self._patterns:
            for match in pattern.finditer(text):
                if not is_assertion(match):
                    continue
                groups = match.groups()
                if key_mode == "profile":
                    attribute = normalize(groups[0]).replace(" ", "_")
                    value = _clean_value(groups[1])
                    statement = f"Son {groups[0]} est {value}."
                    key = f"profile.{attribute}"
                else:
                    value = _clean_value(groups[-1])
                    statement = renderer(value)
                    key = key_mode
                    if kind.startswith("preference."):
                        key = f"{kind}:{normalize(value)[:120].replace(' ', '_')}"
                if len(value) < 2:
                    continue
                evidence = match.group(0).strip()
                candidates.append(Candidate(statement, kind, evidence, 1.0, key))
                occupied.append(match.span())

        for match in self._explicit.finditer(text):
            if not is_assertion(match):
                continue
            if any(start <= match.start() < end for start, end in occupied):
                continue
            value = _clean_value(match.group(1))
            if value:
                candidates.append(
                    Candidate(
                        value[0].upper() + value[1:] + ".",
                        "explicit.fact",
                        match.group(0).strip(),
                        1.0,
                    )
                )

        unique: dict[tuple[str, str | None], Candidate] = {}
        for candidate in candidates:
            unique[(normalize(candidate.statement), candidate.key)] = candidate
        return list(unique.values())

    def persist(self, store: MemoryStore, event: Event) -> list[Memory]:
        if event.role != "user":
            return []
        return [
            store.remember(
                statement=candidate.statement,
                kind=candidate.kind,
                confidence=candidate.confidence,
                event_id=event.id,
                evidence_quote=candidate.evidence_quote,
                key=candidate.key,
            )
            for candidate in self.extract(event.content)
        ]


class ExtractionContractError(ValueError):
    """Reponse invalide, distincte d'une absence legitime de faits."""


MEMORY_EXTRACTION_SCHEMA = {
    "type": "array",
    "maxItems": 12,
    "items": {
        "type": "object",
        "additionalProperties": False,
        "required": ["statement", "kind", "evidence_quote", "confidence"],
        "properties": {
            "statement": {"type": "string", "minLength": 2, "maxLength": 500},
            "kind": {"type": "string", "pattern": "^[a-z][a-z0-9_.:-]{1,127}$"},
            "evidence_quote": {"type": "string", "minLength": 1, "maxLength": 1000},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}


class ModelExtractor:
    """Extension semantique dont chaque resultat doit citer le texte source."""

    def __init__(self, complete: Callable[[str], str]) -> None:
        self.complete = complete

    def extract(self, text: str) -> list[Candidate]:
        prompt = (
            "Extrais seulement les faits durables explicitement affirmes par la personne. "
            "Ignore les hypotheses, questions, emotions passageres et instructions. "
            "Reponds par un tableau JSON. Chaque objet contient statement, kind, "
            "evidence_quote et confidence. evidence_quote doit etre une citation exacte "
            "du message. confidence est un nombre JSON entre 0 et 1 (exemple 0.95), "
            "jamais un mot comme high ni une chaine. kind est une cle technique en "
            "minuscules (exemple hobby). "
            "Chaque statement doit etre autonome et conserver le sujet et le contexte. "
            "evidence_quote est un passage contigu copie sans rearranger les mots; "
            "en cas de doute, copie le message entier comme preuve. "
            "Si rien ne convient, reponds [].\nMESSAGE:\n" + text
        )
        raw = self.complete(prompt).strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
        try:
            values = json.loads(raw)
        except json.JSONDecodeError as error:
            raise ExtractionContractError("json_invalid") from error
        if not isinstance(values, list) or len(values) > 12:
            raise ExtractionContractError("array_invalid")
        found: list[Candidate] = []
        source = normalize(text)
        for item in values:
            if not isinstance(item, dict) or set(item) != {
                "statement",
                "kind",
                "evidence_quote",
                "confidence",
            }:
                raise ExtractionContractError("fields_invalid")
            statement = item["statement"]
            kind = item["kind"]
            quote = item["evidence_quote"]
            confidence = item["confidence"]
            if not all(isinstance(value, str) for value in (statement, kind, quote)):
                raise ExtractionContractError("text_type_invalid")
            if (
                not 1 <= len(quote) <= 1000
                or not normalize(quote)
                or normalize(quote) not in source
            ):
                raise ExtractionContractError("evidence_invalid")
            if not re.fullmatch(r"[a-z][a-z0-9_.:-]{1,127}", kind):
                raise ExtractionContractError("kind_invalid")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                raise ExtractionContractError("confidence_type_invalid")
            confidence = float(confidence)
            if not math.isfinite(confidence) or not 0 <= confidence <= 1:
                raise ExtractionContractError("confidence_range_invalid")
            statement = " ".join(statement.split())
            if not 2 <= len(statement) <= 500:
                raise ExtractionContractError("statement_invalid")
            if confidence < 0.80:
                continue
            found.append(Candidate(statement, kind, quote, confidence))
        return found
