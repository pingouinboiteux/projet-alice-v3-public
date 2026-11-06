"""Separate quoted user data from lexical controls without changing offsets.

This is deliberately not a general natural-language parser. Only explicit
double quotes are data delimiters; French apostrophes remain ordinary text.
Malformed quote pairs fail closed instead of guessing which words are orders.
"""
from __future__ import annotations

OPENERS = {'"': '"', '«': '»', '“': '”'}
CLOSERS = {'»', '”'}


def control_text(text):
    """Mask quoted regions with same-length whitespace; reject malformed pairs."""
    if type(text) is not str:
        raise TypeError('user_text_required')
    output, stack = [], []
    backslashes = 0
    for char in text:
        escaped = backslashes % 2 == 1
        was_quoted = bool(stack)
        delimiter = False
        if not escaped:
            if stack and char == stack[-1]:
                stack.pop()
                delimiter = True
            elif char in OPENERS:
                stack.append(OPENERS[char])
                delimiter = True
            elif char in CLOSERS:
                raise ValueError('unbalanced_user_quotes')
        if was_quoted or stack or delimiter:
            output.append(char if char in '\r\n' else ' ')
        else:
            output.append(char)
        backslashes = backslashes + 1 if char == '\\' else 0
    if stack:
        raise ValueError('unbalanced_user_quotes')
    return ''.join(output)


class ControlPattern:
    """Compiled-pattern search over control text; useful for shared detectors."""
    def __init__(self, pattern):
        self.pattern = pattern.pattern
        self.flags = pattern.flags
        self._compiled = pattern

    def search(self, text, *args, **kwargs):
        try:
            masked = control_text(text)
        except ValueError:
            # Validation emits a clarification for this input. Prompt-state
            # construction must not infer executable controls while it is invalid.
            return None
        return self._compiled.search(masked, *args, **kwargs)
