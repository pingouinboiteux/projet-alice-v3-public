"""Native Sopro using only Alice's original voice sample."""
import json
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def selected_voice():
    name=os.environ.get('ALICE_VOICE_ENGINE','sopro_original')
    if name=='current':
        return {'manifest':'config/voice.lock.json','python':'.venv_voice/Scripts/python.exe',
                'worker':'scripts/voice_worker.py','name':name}
    if name in {'sopro_original','sopro_d'}:
        return {'manifest':'config/voice-sopro.lock.json','python':'.venv_sopro/Scripts/python.exe',
                'worker':'scripts/sopro_worker.py','name':'sopro_original'}
    raise ValueError('Moteur vocal inconnu')

def sopro_settings():
    value=json.loads((ROOT/'config/voice-sopro.lock.json').read_text(encoding='utf-8'))
    for field in ('model','reference'):
        path=Path(value[field])
        if path.is_absolute() or not (ROOT/path).resolve().is_relative_to(ROOT):
            raise ValueError('Chemin vocal hors laboratoire')
    if value['reference']!='models/voice/reference_alice.wav':
        raise ValueError('Sopro doit utiliser uniquement le sample original Alice')
    if value['steps']!=2 or value['language']!='fr':raise ValueError('Profil Sopro modifie sans validation')
    return value
