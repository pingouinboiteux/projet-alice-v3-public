"""Paired full-file/capture ASR diagnosis on identical synthetic audio.

The caller owns the protected session. No microphone or audio output is opened.
These comparisons isolate the capture path, not synthesis versus ASR mistakes.
"""
from __future__ import annotations

import audioop
import hashlib
from pathlib import Path
import re
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
PHRASES = (
    'Alice, crée une note avec le titre Jardin et le texte Arroser les fleurs.',
    'Alice, crée une note avec le titre Matériel et le texte Un arroseur automatique est installé.',
    'Alice, crée une note avec le titre Courses et le texte Acheter du pain et du lait.',
    'Alice, crée une note avec le titre Rendez-vous et le texte Le rendez-vous est à 09:15 et coûte 15,60 euros.',
)


def words(text):
    """Ignore case, punctuation and whitespace only; never repair words/digits."""
    return re.findall(r'\w+', text.casefold(), flags=re.UNICODE)


def compare_words(expected, actual):
    reference, hypothesis = words(expected), words(actual)
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j - 1] + (left != right)))
        previous = current
    return {'word_match': reference == hypothesis, 'word_edit_distance': previous[-1],
            'reference_words': len(reference),
            'normalization': 'case, punctuation and whitespace only; numbers not verbalized'}


def run_diagnosis(session):
    """Return JSON evidence; temporary WAVs are removed even after a failure."""
    from voice_link import Voice
    from hearing_link import Hearing

    session.check()
    if session.voice is not None:
        raise RuntimeError('Diagnosis requires a session without an active voice')
    folder = Path(session.temp.name).resolve()
    if not folder.is_relative_to(ROOT.resolve()) or not folder.name.startswith('validation_'):
        raise RuntimeError('Private validation session required')
    voice = session.voice = Voice(session)
    hearing = Hearing(session)
    paths, rows = [], []
    report = {'scope': 'synthetic paired file ASR, same bytes with capture off/on; no microphone or playback',
              'limit': 'Synthesis and ASR both contribute; this does not isolate either one as the error source.',
              'rows': rows}
    try:
        started = time.perf_counter()
        voice.start()
        report['voice_start_seconds'] = time.perf_counter() - started
        for index, text in enumerate(PHRASES):
            session.check()
            started = time.perf_counter()
            frames = []
            for part, _info in voice.audio_parts(text):
                with wave.open(str(part), 'rb') as wav:
                    if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 24000):
                        raise RuntimeError('Unexpected synthesis format')
                    frames.append(wav.readframes(wav.getnframes()))
            if not frames:
                raise RuntimeError('No synthesis frames')
            pcm, _ = audioop.ratecv(b''.join(frames), 2, 1, 24000, 16000, None)
            path = folder / f'validation_audio_pair_{index}.wav'
            paths.append(path)
            with wave.open(str(path), 'wb') as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(pcm)
            rows.append({'id': f'validation_audio_pair_{index}', 'source_text': text,
                         'synthesis_seconds': time.perf_counter() - started,
                         'input_audio_seconds': len(pcm) / 32000,
                         'wav_sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
        voice.close()
        session.voice = None
        started = time.perf_counter()
        hearing.start()
        report['hearing_start_seconds'] = time.perf_counter() - started
        for row, path in zip(rows, paths):
            # Alternate order to avoid confounding all capture comparisons with
            # the immediately preceding full-file inference and wake state.
            modes = [('full_file', False), ('captured', True)]
            if int(row['id'].rsplit('_', 1)[1]) % 2:
                modes.reverse()
            row['order'] = [label for label, _ in modes]
            for label, capture in modes:
                session.check()
                if hashlib.sha256(path.read_bytes()).hexdigest() != row['wav_sha256']:
                    raise RuntimeError('Paired input changed')
                started = time.perf_counter()
                result = hearing.command('transcribe', file=path.relative_to(ROOT).as_posix(),
                                         validate_capture=capture)
                row[label] = {'result': result, 'wall_seconds': time.perf_counter() - started,
                              'source_comparison': compare_words(row['source_text'], result.get('text', ''))}
            row['same_raw_transcript'] = row['full_file']['result'].get('text') == row['captured']['result'].get('text')
            row['same_words'] = words(row['full_file']['result'].get('text', '')) == words(row['captured']['result'].get('text', ''))
            row['capture_duration_delta_seconds'] = (
                row['captured']['result'].get('audio_seconds', 0) - row['full_file']['result'].get('audio_seconds', 0))
            path.unlink(missing_ok=True)
        report['status'] = 'complete'
        return report
    finally:
        try:
            hearing.close()
        finally:
            try:
                if session.voice is not None:
                    voice.close()
            finally:
                session.voice = None
                for path in paths:
                    path.unlink(missing_ok=True)
