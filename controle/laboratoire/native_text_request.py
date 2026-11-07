"""Explicit local requests to type literal text into a named native window.

Parsing grants no window access and performs no action. Ambiguous references
are clarified. Source metadata must come from the local input boundary.
"""
import re

PREFIX = (r"\s*(?:alice\s*[,!:]?\s*)?"
          r"(?:(?:peux[- ]tu|pourrais[- ]tu|tu peux|tu pourrais)\s+)?"
          r"(?:[eé]cris|[eé]crire|tape|taper|saisis|saisir)\s+")
QUOTE = r'(?:«(?P<{name}>[^«»]+)»|"(?P<{name}_ascii>[^\"]+)")'
WINDOW = r'(?:la\s+fen[eê]tre\s+' + QUOTE.format(name='window') + r'|(?:le\s+)?(?P<notepad>bloc[- ]notes))'
BODY = QUOTE.format(name='body')
PATTERNS = [
    re.compile(PREFIX + r'(?:le\s+texte\s+)?' + BODY + r'\s+dans\s+' + WINDOW + r'\s*[.!?]?\s*', re.I),
    re.compile(PREFIX + r'dans\s+' + WINDOW + r'\s+(?:le\s+)?texte\s+' + BODY + r'\s*[.!?]?\s*', re.I),
]
TAIL = re.compile(PREFIX + r'dans\s+' + WINDOW + r'\s+(?:le\s+)?texte\s*:\s*(?P<body_tail>.+)', re.I | re.S)
NATIVE = re.compile(r'\b(?:fen[eê]tre|bloc[- ]notes)\b', re.I)
START = re.compile(PREFIX, re.I)


def interpret(text, source):
    if source not in ('text', 'voice'):
        raise ValueError('native_local_source_required')
    if type(text) is not str or not text.strip() or len(text) > 6000:
        return {'status':'clarify'}
    if not START.match(text) or not NATIVE.search(text):
        return {'status':'not_handled'}
    match = next((m for pattern in PATTERNS if (m := pattern.fullmatch(text))), None)
    if match is None: match = TAIL.fullmatch(text)
    if match is None:
        return {'status':'clarify', 'reply':'Precise la fenetre et le texte exact a saisir.'}
    groups = match.groupdict()
    window_key = 'window' if groups.get('window') is not None else 'window_ascii'
    body_key = next((k for k in ('body','body_ascii','body_tail') if groups.get(k) is not None), None)
    hint = 'Bloc-notes' if groups.get('notepad') else groups.get(window_key)
    body = groups[body_key]
    # A tail containing a quote delimiter is ambiguous; do not type delimiters
    # accidentally when the user intended the quoted form.
    if body_key=='body_tail' and any(c in body for c in '«»"'):
        return {'status':'clarify'}
    if (not hint or not hint.strip() or len(hint)>200 or any(c in hint for c in '\r\n\x00')
            or not body.strip() or len(body)>4000
            or any(ord(c)<32 and c not in '\n\t' for c in body)):
        return {'status':'clarify'}
    return {'status':'ready', 'target':{'window_hint':hint,'text':body},
            'text_span':list(match.span(body_key)), 'source':source}
