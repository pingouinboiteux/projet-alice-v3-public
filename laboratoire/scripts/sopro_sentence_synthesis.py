"""Candidate only: finish each sentence acoustically before emitting its PCM."""
from alice.voice.text import sentences


def sentence_audio(model, text, reference, language='fr'):
    for sentence in sentences(text):
        yield model.synthesize(sentence, ref=reference, lang=language)
