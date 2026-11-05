"""Strict stop-only vocabulary; never forward unrelated speech to dialogue."""
import re


def is_stop_command(text):
    words = re.findall(r"\w+", text.casefold())
    return words in (['stop'], ['alice', 'stop'])
