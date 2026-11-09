"""Stage and explicitly review one laboratory Python file per code mission."""
import difflib
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from codex_link import ROOT

BACKUPS = ROOT / 'data/sauvegardes/code_missions'
DENIED = {'codex_link.py', 'code_missions.py', 'code_promotion.py',
          'autonomy_policy.py', 'chat.py', 'alice_desktop.py'}
MAX_SOURCE_BYTES = 256 * 1024
MAX_DIFF_CHARS = 12000


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _preserve_line_endings(original, candidate):
    if b'\r' in original.replace(b'\r\n', b'') or b'\r' in candidate.replace(b'\r\n', b''):
        raise ValueError('Fins de ligne non standards dans le fichier.')
    if b'\n' in original.replace(b'\r\n', b'') and b'\r\n' in original:
        raise ValueError('Fins de ligne mixtes dans le fichier original.')
    lines = candidate.replace(b'\r\n', b'\n')
    return lines.replace(b'\n', b'\r\n') if b'\r\n' in original else lines


def _source(relative):
    if type(relative) is not str or '\\' in relative or ':' in relative:
        raise ValueError('Chemin de source invalide.')
    parts = Path(relative).parts
    if len(parts) != 2 or parts[0] != 'scripts' or parts[1] in DENIED or not parts[1].endswith('.py'):
        raise ValueError('Seul un module Python ordinaire de laboratoire/scripts est admissible.')
    path = ROOT.joinpath(*parts)
    if path.resolve(strict=True).parent != (ROOT / 'scripts').resolve(strict=True):
        raise ValueError('Source hors du dossier autorise.')
    details = path.lstat()
    if path.is_symlink() or details.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or details.st_nlink != 1:
        raise ValueError('Lien de source refuse.')
    if not path.is_file() or details.st_size > MAX_SOURCE_BYTES:
        raise ValueError('Fichier source absent ou trop grand.')
    return path


def stage(relative):
    data = _source(relative).read_bytes()
    data.decode('utf-8')
    return data, _hash(data)


def proposal(relative, expected_sha, workspace):
    original = _source(relative)
    workspace = Path(workspace).resolve(strict=True)
    candidate = workspace / relative
    if not candidate.is_file() or candidate.is_symlink():
        raise ValueError('Copie modifiee absente.')
    if not candidate.resolve(strict=True).is_relative_to(workspace):
        raise ValueError('Copie modifiee hors atelier.')
    details = candidate.lstat()
    if details.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT or details.st_nlink != 1 or details.st_size > MAX_SOURCE_BYTES:
        raise ValueError('Copie modifiee non admissible.')
    current = original.read_bytes()
    if _hash(current) != expected_sha:
        raise ValueError('Le fichier original a change depuis la copie : nouvelle mission requise.')
    changed = _preserve_line_endings(current, candidate.read_bytes())
    if changed == current:
        raise ValueError('Aucune modification a appliquer.')
    old_text = current.decode('utf-8')
    new_text = changed.decode('utf-8')
    compile(new_text, str(candidate), 'exec')
    diff = ''.join(difflib.unified_diff(old_text.splitlines(keepends=True),
        new_text.splitlines(keepends=True), fromfile=relative+' (actuel)',
        tofile=relative+' (propose)'))
    if not diff or len(diff) > MAX_DIFF_CHARS:
        raise ValueError('Difference trop grande pour une confirmation fiable.')
    return original, current, changed, diff


def apply(identity, relative, expected_sha, workspace, confirm):
    original, current, changed, diff = proposal(relative, expected_sha, workspace)
    description = ('Appliquer cette modification au laboratoire ?\n'
                   + str(original) + '\n\n' + diff + '\n\n'
                   'Une copie de retour sera conservee avant remplacement.')
    if not confirm(description):
        return False
    # Confirm may take minutes. Never overwrite a file edited during the dialog.
    if _hash(_source(relative).read_bytes()) != expected_sha:
        raise ValueError('Le fichier original a change pendant la confirmation.')
    backup = BACKUPS / identity / relative
    backup.parent.mkdir(parents=True, exist_ok=False)
    with backup.open('xb') as stream:
        stream.write(current)
        stream.flush()
        os.fsync(stream.fileno())
    if backup.read_bytes() != current:
        raise OSError('Copie de retour non verifiee.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.alice_candidate_', suffix='.py',
                                         dir=original.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(changed)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, original)
        if _hash(original.read_bytes()) != _hash(changed):
            os.replace(backup, original)
            raise OSError('Verification apres application echouee ; original restaure.')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True


def restore(identity, relative, expected_sha, workspace, confirm):
    original = _source(relative)
    backup = BACKUPS / identity / relative
    if not backup.is_file() or backup.is_symlink() or backup.lstat().st_nlink != 1:
        raise ValueError('Copie de retour absente.')
    old = backup.read_bytes()
    if _hash(old) != expected_sha:
        raise ValueError('Copie de retour non conforme a la version source.')
    candidate = Path(workspace) / relative
    if not candidate.is_file() or candidate.is_symlink() or not candidate.resolve(strict=True).is_relative_to(Path(workspace).resolve(strict=True)):
        raise ValueError('Copie de mission invalide.')
    proposed = _preserve_line_endings(old, candidate.read_bytes())
    current = original.read_bytes()
    if current != proposed:
        raise ValueError('Le fichier a change depuis l application ; restauration manuelle requise.')
    previous_text = old.decode('utf-8')
    current_text = current.decode('utf-8')
    diff = ''.join(difflib.unified_diff(current_text.splitlines(keepends=True),
        previous_text.splitlines(keepends=True), fromfile=relative+' (actuel)',
        tofile=relative+' (restaure)'))
    if not diff or len(diff) > MAX_DIFF_CHARS:
        raise ValueError('Restauration impossible a presenter clairement.')
    if not confirm('Restaurer cette ancienne version ?\n'+str(original)+'\n\n'+diff):
        return False
    if _source(relative).read_bytes() != current:
        raise ValueError('Le fichier a change pendant la confirmation.')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.alice_restore_', suffix='.py',
                                         dir=original.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(old)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, original)
        if original.read_bytes() != old:
            raise OSError('Verification de la restauration echouee.')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return True
