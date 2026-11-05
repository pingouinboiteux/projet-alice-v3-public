"""Refus des syntheses inachevees avant conversion et lecture audio."""

from __future__ import annotations

from functools import wraps


class UnsafeSynthesisError(RuntimeError):
    """Un bloc douteux doit rester silencieux, jamais etre tronque puis joue."""


def maximum_audio_seconds(text: str) -> float:
    # Marge volontairement large pour pauses, nombres et prononciation lente.
    return min(30.0, max(8.0, 4.0 + len(text) / 7.0))


def require_complete_inference(inference, stop_token: int):
    """Le moteur retourne aussi les jetons quand son budget est epuise sans EOS."""

    @wraps(inference)
    def checked(*args, **kwargs):
        tokens = inference(*args, **kwargs)
        if tokens.shape[-1] == 0 or not bool((tokens[:, -1] == stop_token).all()):
            raise UnsafeSynthesisError("generation vocale sans marque de fin")
        return tokens

    return checked


def validate_audio_length(text: str, samples: int, sample_rate: int) -> None:
    if samples <= 0 or samples / sample_rate > maximum_audio_seconds(text):
        raise UnsafeSynthesisError("duree vocale incompatible avec le bloc de texte")
