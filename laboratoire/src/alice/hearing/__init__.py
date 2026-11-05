"""Transcription et detection de fin de parole."""

from alice.hearing.capture import SpeechCapture, WakeWindow
from alice.hearing.turn import TurnDetector

__all__ = ["SpeechCapture", "TurnDetector", "WakeWindow"]
