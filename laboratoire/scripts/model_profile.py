"""Pinned local model settings; no model inference or storage at import."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def relative_path(value,base=ROOT):
    path=Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Model resource path must remain relative')
    resolved=(base/path).resolve()
    if not resolved.is_relative_to(base.resolve()):raise ValueError('Model resource outside laboratory')
    return resolved

def load_profile():
    return json.loads((ROOT/'config/model.lock.json').read_text(encoding='utf-8'))

def template_settings(spec):
    if spec.get('family')!='gemma4':raise ValueError('Alice requires its verified Gemma model')
    return {'enable_thinking':False}

def verify_resources(spec):
    template_settings(spec)
    model=relative_path(spec['file'],ROOT/'models')
    if not model.is_file() or model.stat().st_size!=spec['bytes']:raise RuntimeError('Modele absent ou incomplet')
    marker=relative_path(spec['verification_file'])
    verified=json.loads(marker.read_text(encoding='utf-8'))
    if verified['sha256']!=spec['sha256'] or verified['status']!='download_verified':raise RuntimeError('Poids non verifies')
    runtime=relative_path(spec['runtime_directory'])
    manifest=relative_path(spec['runtime_manifest'])
    pinned=json.loads(manifest.read_text(encoding='utf-8'))['files']
    if 'llama-server.exe' not in pinned:raise RuntimeError('Moteur non verrouille')
    for name,expected in pinned.items():
        path=relative_path(name,runtime)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:
            raise RuntimeError('Moteur absent ou modifie : '+name)
    return model,runtime/'llama-server.exe'
