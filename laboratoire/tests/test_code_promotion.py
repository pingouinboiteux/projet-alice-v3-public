from pathlib import Path
from unittest.mock import Mock

import pytest

import code_promotion


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(code_promotion, 'ROOT', tmp_path)
    monkeypatch.setattr(code_promotion, 'BACKUPS', tmp_path / 'data/backups')
    source = tmp_path / 'scripts/example.py'
    source.parent.mkdir()
    source.write_text('value = 1\n', encoding='utf-8')
    workspace = tmp_path / 'atelier/mission'
    (workspace / 'scripts').mkdir(parents=True)
    return source, workspace


def test_staged_python_change_requires_diff_confirmation_and_keeps_backup(project):
    source, workspace = project
    original, digest = code_promotion.stage('scripts/example.py')
    assert original == source.read_bytes()
    candidate = workspace / 'scripts/example.py'
    candidate.write_text('value = 2\n', encoding='utf-8')
    approve = Mock(return_value=False)
    assert not code_promotion.apply('validation_1', 'scripts/example.py', digest, workspace, approve)
    assert source.read_bytes() == original
    assert '-value = 1' in approve.call_args.args[0]
    approve.return_value = True
    assert code_promotion.apply('validation_1', 'scripts/example.py', digest, workspace, approve)
    assert source.read_text(encoding='utf-8') == 'value = 2\n'
    assert (code_promotion.BACKUPS/'validation_1/scripts/example.py').read_bytes() == original


def test_changed_original_and_invalid_candidate_are_refused(project):
    source, workspace = project
    _, digest = code_promotion.stage('scripts/example.py')
    candidate = workspace / 'scripts/example.py'
    candidate.write_text('def broken(:\n', encoding='utf-8')
    with pytest.raises(SyntaxError):
        code_promotion.proposal('scripts/example.py', digest, workspace)
    candidate.write_text('value = 2\n', encoding='utf-8')
    source.write_text('value = 3\n', encoding='utf-8')
    with pytest.raises(ValueError, match='change'):
        code_promotion.apply('validation_2', 'scripts/example.py', digest, workspace, Mock())
    assert source.read_text(encoding='utf-8') == 'value = 3\n'


def test_candidate_keeps_original_line_endings(project):
    source, workspace = project
    source.write_bytes(b'value = 1\n')
    _, digest = code_promotion.stage('scripts/example.py')
    (workspace/'scripts/example.py').write_bytes(b'value = 2\r\n')
    _, _, changed, diff = code_promotion.proposal('scripts/example.py', digest, workspace)
    assert changed == b'value = 2\n'
    assert '+value = 2' in diff


def test_restore_refuses_to_overwrite_later_edits(project):
    source, workspace = project
    _, digest = code_promotion.stage('scripts/example.py')
    (workspace/'scripts/example.py').write_text('value = 2\n', encoding='utf-8')
    assert code_promotion.apply('validation_3', 'scripts/example.py', digest, workspace, lambda _: True)
    source.write_text('value = 3\n', encoding='utf-8')
    with pytest.raises(ValueError, match='change'):
        code_promotion.restore('validation_3', 'scripts/example.py', digest, workspace, Mock())
    assert source.read_text(encoding='utf-8') == 'value = 3\n'


def test_sensitive_modules_and_parent_paths_cannot_be_staged(project):
    for name in ('scripts/codex_link.py', 'scripts/../example.py', '../scripts/example.py'):
        with pytest.raises((ValueError, FileNotFoundError)):
            code_promotion.stage(name)
