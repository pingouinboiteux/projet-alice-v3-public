"""Machine a etats pure pour transformer les trames du micro en tours."""

from __future__ import annotations

import re
import unicodedata
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CapturedSpeech:
    audio: np.ndarray
    speech_seconds: float
    silence_seconds: float
    end_reason: str


@dataclass(frozen=True)
class WakeDecision:
    accepted: bool
    cleaned: str
    reason: str
    remaining_seconds: float
    nearest_name_distance: int | None


class SpeechCapture:
    def __init__(
        self,
        *,
        sample_rate: int = 16000,
        frame_samples: int = 480,
        minimum_speech_seconds: float = 0.5,
        short_silence_seconds: float = 0.6,
        fixed_silence_seconds: float = 1.3,
        maximum_silence_seconds: float = 2.8,
        turn_confidence: float = 0.9,
        maximum_utterance_seconds: float = 120.0,
        turn_probability: Callable[[np.ndarray], float | None] | None = None,
    ) -> None:
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.minimum_speech_frames = max(
            1, round(minimum_speech_seconds * sample_rate / frame_samples)
        )
        self.short_silence_frames = max(
            1, round(short_silence_seconds * sample_rate / frame_samples)
        )
        self.fixed_silence_frames = max(
            1, round(fixed_silence_seconds * sample_rate / frame_samples)
        )
        self.maximum_silence_frames = max(
            1, round(maximum_silence_seconds * sample_rate / frame_samples)
        )
        self.maximum_frames = max(
            1, round(maximum_utterance_seconds * sample_rate / frame_samples)
        )
        self.turn_confidence = turn_confidence
        self.turn_probability = turn_probability
        self.preroll = deque(maxlen=max(1, round(0.3 * sample_rate / frame_samples)))
        self._reset()

    def _reset(self) -> None:
        self.active = False
        self.frames: list[np.ndarray] = []
        self.speech_frames = 0
        self.silence_frames = 0
        self.judged = False
        self.extended = False

    def feed(self, frame: np.ndarray, speaking: bool) -> CapturedSpeech | None:
        values = np.asarray(frame, dtype=np.float32).reshape(-1)
        if len(values) != self.frame_samples:
            raise ValueError("taille de trame invalide")
        if not self.active:
            self.preroll.append(values.copy())
            if not speaking:
                return None
            self.active = True
            self.frames = list(self.preroll)
            self.speech_frames = 1
            self.silence_frames = 0
            return None

        self.frames.append(values.copy())
        if speaking:
            self.speech_frames += 1
            self.silence_frames = 0
            self.judged = False
            self.extended = False
        else:
            self.silence_frames += 1

        if len(self.frames) >= self.maximum_frames:
            return self._finish("maximum_duration")
        if self.speech_frames < self.minimum_speech_frames:
            if self.silence_frames >= self.fixed_silence_frames:
                self._reset()
            return None

        if self.silence_frames >= self.short_silence_frames and not self.judged:
            self.judged = True
            if self.turn_probability is not None:
                probability = self.turn_probability(np.concatenate(self.frames))
                if probability is not None:
                    if probability >= self.turn_confidence:
                        return self._finish("intonation")
                    self.extended = True

        limit = (
            self.maximum_silence_frames if self.extended else self.fixed_silence_frames
        )
        if self.silence_frames >= limit:
            return self._finish("silence")
        return None

    def _finish(self, reason: str) -> CapturedSpeech:
        frames = self.frames
        speech = self.speech_frames * self.frame_samples / self.sample_rate
        silence = self.silence_frames * self.frame_samples / self.sample_rate
        result = CapturedSpeech(np.concatenate(frames), speech, silence, reason)
        self.preroll.clear()
        self._reset()
        return result


class WakeWindow:
    def __init__(
        self,
        name: str = "Alice",
        window_seconds: float = 60.0,
        aliases: Sequence[str] = (),
    ) -> None:
        self.name = self._normalize(name)
        self.aliases = tuple(
            alias
            for alias in (self._normalize(value).strip() for value in aliases)
            if alias and alias != self.name
        )
        self.window_seconds = max(1.0, float(window_seconds))
        self.open_until = 0.0

    @staticmethod
    def _normalize(text: str) -> str:
        folded = unicodedata.normalize("NFKD", text.casefold())
        return "".join(
            char for char in folded if not unicodedata.combining(char)
        ).replace("’", "'")

    @staticmethod
    def _distance(left: str, right: str) -> int:
        previous = list(range(len(right) + 1))
        for row, left_character in enumerate(left, start=1):
            current = [row]
            for column, right_character in enumerate(right, start=1):
                current.append(
                    min(
                        current[-1] + 1,
                        previous[column] + 1,
                        previous[column - 1] + int(left_character != right_character),
                    )
                )
            previous = current
        return previous[-1]

    def _nearest_distance(self, normalized: str) -> int | None:
        words = re.findall(r"[a-z]+", normalized)
        if not words:
            return None
        return min(self._distance(word, self.name) for word in words)

    @staticmethod
    def _pattern(values: Sequence[str]) -> str:
        alternatives = "|".join(
            sorted((re.escape(value) for value in values), key=len, reverse=True)
        )
        return rf"\b(?:{alternatives})\b[\s,.:;!?-]*"

    def extend(self, now: float) -> float:
        self.open_until = max(self.open_until, now + self.window_seconds)
        return self.open_until - now

    def decide(self, text: str, now: float) -> WakeDecision:
        normalized = self._normalize(text)
        exact_match = re.search(self._pattern((self.name,)), normalized)
        alias_match = (
            re.search(self._pattern(self.aliases), normalized) if self.aliases else None
        )
        match = exact_match or alias_match
        addressed = match is not None
        if addressed:
            self.open_until = now + self.window_seconds
        inside_window = now <= self.open_until
        if match is not None:
            cleaned = (text[: match.start()] + text[match.end() :]).strip(" ,.:;!?-")
        else:
            cleaned = text.strip()
        accepted = (addressed or inside_window) and bool(cleaned)
        if accepted:
            self.extend(now)
        if exact_match is not None:
            reason = "exact_name" if cleaned else "exact_name_only"
        elif alias_match is not None:
            reason = "name_alias" if cleaned else "name_alias_only"
        elif accepted:
            reason = "open_window"
        else:
            reason = "closed_window"
        return WakeDecision(
            accepted,
            cleaned,
            reason,
            max(0.0, self.open_until - now),
            self._nearest_distance(normalized),
        )

    def accept(self, text: str, now: float) -> tuple[bool, str]:
        decision = self.decide(text, now)
        return decision.accepted, decision.cleaned
