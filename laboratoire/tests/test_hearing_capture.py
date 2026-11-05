from __future__ import annotations

import numpy as np

from alice.hearing.capture import SpeechCapture, WakeWindow


def frame() -> np.ndarray:
    return np.ones(480, dtype=np.float32) * 0.1


def test_confident_intonation_finishes_early():
    capture = SpeechCapture(turn_probability=lambda _audio: 0.95)
    for _ in range(20):
        assert capture.feed(frame(), True) is None
    result = None
    for _ in range(25):
        result = capture.feed(frame() * 0, False)
        if result:
            break
    assert result is not None
    assert result.end_reason == "intonation"
    assert result.silence_seconds < 1.0


def test_uncertain_intonation_gives_the_speaker_more_time():
    capture = SpeechCapture(turn_probability=lambda _audio: 0.05)
    for _ in range(20):
        capture.feed(frame(), True)
    result = None
    for _ in range(100):
        result = capture.feed(frame() * 0, False)
        if result:
            break
    assert result is not None
    assert result.end_reason == "silence"
    assert result.silence_seconds >= 2.7


def test_short_noise_is_discarded():
    capture = SpeechCapture()
    for _ in range(4):
        capture.feed(frame(), True)
    results = [capture.feed(frame() * 0, False) for _ in range(60)]
    assert all(result is None for result in results)


def test_wake_name_opens_a_bounded_conversation_window():
    wake = WakeWindow(window_seconds=60)
    accepted, cleaned = wake.accept("Alice, raconte-moi quelque chose.", 100.0)
    assert accepted is True
    assert cleaned == "raconte-moi quelque chose"
    assert wake.accept("Et ensuite ?", 150.0)[0] is True
    assert wake.accept("Tu es la ?", 211.0)[0] is False


def test_accepted_follow_up_slides_the_conversation_window():
    wake = WakeWindow(window_seconds=60)
    assert wake.accept("Alice, tu es la ?", 100.0)[0] is True
    assert wake.accept("Et ensuite ?", 150.0)[0] is True
    assert wake.accept("Tu m'ecoutes toujours ?", 205.0)[0] is True
    assert wake.accept("Trop tard ?", 266.0)[0] is False


def test_wake_window_can_be_restarted_after_alice_finishes_speaking():
    wake = WakeWindow(window_seconds=60)
    assert wake.accept("Alice, reponds-moi.", 100.0)[0] is True
    assert wake.extend(140.0) == 60.0
    assert wake.accept("Je peux continuer ?", 199.0)[0] is True


def test_close_name_alias_wakes_alice_and_is_removed():
    wake = WakeWindow(window_seconds=60, aliases=["alise", "alys", "alicee"])
    decision = wake.decide("Alisse, est-ce que tu m'entends ?", 100.0)

    assert decision.accepted is False
    assert decision.reason == "closed_window"
    assert decision.nearest_name_distance == 2

    decision = wake.decide("Alys, est-ce que tu m'entends ?", 110.0)
    assert decision.accepted is True
    assert decision.cleaned == "est-ce que tu m'entends"
    assert decision.reason == "name_alias"


def test_configured_alisse_variant_wakes_alice():
    wake = WakeWindow(window_seconds=60, aliases=["alisse"])

    decision = wake.decide("Alisse, tu m'entends ?", 100.0)

    assert decision.accepted is True
    assert decision.cleaned == "tu m'entends"


def test_common_homophone_does_not_wake_alice():
    wake = WakeWindow(window_seconds=120, aliases=["alise", "alys"])

    decision = wake.decide("Allez, on recommence le niveau.", 100.0)

    assert decision.accepted is False
    assert decision.reason == "closed_window"
