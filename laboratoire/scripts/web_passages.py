"""Bounded lexical selection with exact offsets into already extracted page text.

This is retrieval, not proof that an answer exists. No network, model or storage.
The caller must preserve truncation metadata and distinguish absence in these
passages from absence on the whole page. Accents are ignored only for matching.
"""
import math
import re
import unicodedata
from collections import Counter

MAX_BYTES = 1024 * 1024
MAX_BUDGET = 10000
_URL = re.compile(r'https?://\S+', re.I)
_WORDS = re.compile(r'[^\W_]+', re.UNICODE)
_STOP = set(('a au aux avec ce ces cet cette dans de des du elle elles en et est '
    'il ils je la le les leur lui ma mais me mes mon ne nos notre nous on ou par '
    'pas pour qu que quel quelle quelles quels qui sa sans se ses son sont sous '
    'sur ta te tes ton tu un une vos votre vous y lire lis page web site internet '
    'retrouve trouver information informations peux peut pourrais donne dit dis '
    'merci stp pourquoi comment').split())


def _terms(value):
    plain = unicodedata.normalize('NFKD', _URL.sub(' ', value).casefold())
    plain = ''.join(char for char in plain if not unicodedata.combining(char))
    return {word for word in _WORDS.findall(plain)
            if len(word) > 1 and word not in _STOP}


def _chunks(text, width):
    start = 0
    overlap = min(180, width // 5)
    while start < len(text):
        end = min(start + width, len(text))
        if end < len(text):
            boundary = max(text.rfind(' ', start + width * 3 // 4, end),
                           text.rfind('\n', start + width * 3 // 4, end))
            if boundary > start:
                end = boundary + 1
        yield start, end
        if end == len(text):
            break
        start = end - overlap


def _merged(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def select_passages(text, question, budget=10000):
    """Return exact text passages and coverage metadata, using at most budget chars.

    Input is extracted (optionally whitespace-normalized) page text. Offsets use
    Python string indices into that exact input, never into the HTML response.
    budget is an integer from256 to10000; text is at most1MiB UTF-8 and question
    at most2000 characters. Reject oversized input instead of silently losing it.
    """
    if type(text) is not str or type(question) is not str:
        raise ValueError('page_text_and_question_required')
    if len(text) > MAX_BYTES or len(text.encode('utf-8')) > MAX_BYTES:
        raise ValueError('page_text_limit')
    if len(question) > 2000:
        raise ValueError('question_limit')
    if type(budget) is not int or not 256 <= budget <= MAX_BUDGET:
        raise ValueError('passage_budget_limit')
    if len(text) <= budget:
        chosen = [(0, len(text))] if text else []
    else:
        terms = _terms(question)
        candidates = [(start, end, _terms(text[start:end]) & terms)
                      for start, end in _chunks(text, min(1000, budget))]
        counts = Counter(term for _, _, matches in candidates for term in matches)
        weights = {term: 1 + math.log((len(candidates) + 1) / (count + 1))
                   for term, count in counts.items()}
        chosen, covered = [], set()
        remaining = list(candidates)
        while remaining:
            # Reward newly covered query terms so multiple requested fields can
            # survive, rather than filling the budget with one repeated keyword.
            ranked = sorted(remaining, key=lambda item: (
                -sum(weights[t] * (3 if t not in covered else 1) for t in item[2]),
                item[0]))
            for candidate in ranked:
                start, end, matches = candidate
                merged = _merged(chosen + [(start, end)])
                size = sum(right - left for left, right in merged)
                if size <= budget:
                    remaining.remove(candidate)
                    chosen = merged
                    covered.update(matches)
                    break
            else:
                break
            if size == budget:
                break
    passages = [{'id': f'p{index}', 'start': start, 'end': end,
                 'text': text[start:end]}
                for index, (start, end) in enumerate(chosen, 1)]
    selected = sum(len(passage['text']) for passage in passages)
    return {'passages': passages, 'total_chars': len(text),
            'selected_chars': selected, 'truncated': selected < len(text)}
