import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from code_missions import CodeMissions, MissionStore, command
from codex_link import _size, _workspace, run_task


def test_explicit_code_commands_only():
    assert command('/faire cree un fichier') == ('new', 'cree un fichier')
    assert command("dans l'atelier cree un fichier") == ('new', 'cree un fichier')
    assert command('/missions') == ('list', None)
    assert command('/faire fichier scripts/example.py : corrige le calcul') == (
        'new_file', ('scripts/example.py', 'corrige le calcul'))
    assert command('/appliquer abcdef123456') == ('apply', 'abcdef123456')
    assert command('/restaurer-code abcdef123456') == ('restore', 'abcdef123456')
    assert command('Parlons de code') is None


def test_journal_recovers_interrupted_mission(tmp_path):
    database = tmp_path / 'private/missions.sqlite3'
    workspaces = tmp_path / 'atelier/missions'
    store = MissionStore(database, workspaces)
    mission = store.create('Cree validation.txt')
    store.start(mission['id'])
    recovered = MissionStore(database, workspaces)
    assert recovered.get(mission['id'])['state'] == 'interrupted'
    runner = Mock(return_value={'status':'completed', 'changed_files':['validation.txt'],
                                'message':'fini', 'seconds':2})
    controller = CodeMissions(Mock(), store=recovered, runner=runner)
    reply = controller.handle('/reprendre ' + mission['id'], 'text')
    assert 'executee' in reply
    assert recovered.get(mission['id'])['attempts'] == 2
    assert recovered.get(mission['id'])['state'] == 'executed'
    runner.assert_called_once()


def test_public_source_cannot_create_a_mission(tmp_path):
    store = MissionStore(tmp_path / 'missions.sqlite3', tmp_path / 'atelier')
    with pytest.raises(PermissionError):
        CodeMissions(Mock(), store=store, runner=Mock()).handle('/faire execute ceci', 'twitch')
    assert store.list() == []


def test_staged_source_can_be_applied_only_after_review(tmp_path, monkeypatch):
    import code_promotion
    import codex_link
    monkeypatch.setattr(codex_link, 'ATELIER', tmp_path / 'atelier')
    monkeypatch.setattr(code_promotion, 'ROOT', tmp_path)
    monkeypatch.setattr(code_promotion, 'BACKUPS', tmp_path / 'data/backups')
    source = tmp_path / 'scripts/example.py'
    source.parent.mkdir()
    source.write_text('value = 1\n', encoding='utf-8')
    store = MissionStore(tmp_path / 'data/missions.sqlite3', tmp_path / 'atelier/missions')
    def runner(session, prompt, workspace, **kwargs):
        (workspace/'scripts/example.py').write_text('value = 2\n', encoding='utf-8')
        return {'status':'completed', 'changed_files':['scripts/example.py'], 'message':'', 'seconds':1}
    approve = Mock(return_value=True)
    controller = CodeMissions(Mock(), store=store, runner=runner, confirm=approve)
    controller.handle('/faire fichier scripts/example.py : change value', 'text')
    identity = store.list(1)[0]['id']
    assert store.get(identity)['state'] == 'executed'
    assert source.read_text(encoding='utf-8') == 'value = 1\n'
    controller.handle('/appliquer ' + identity, 'text')
    assert source.read_text(encoding='utf-8') == 'value = 2\n'
    assert store.get(identity)['state'] == 'applied'
    controller.handle('/restaurer-code ' + identity, 'text')
    assert source.read_text(encoding='utf-8') == 'value = 1\n'
    assert store.get(identity)['state'] == 'restored'
    assert approve.call_count == 2


def test_workspace_must_stay_inside_atelier_and_reject_hardlinks(tmp_path, monkeypatch):
    import codex_link
    monkeypatch.setattr(codex_link, 'ATELIER', tmp_path / 'atelier')
    (tmp_path / 'atelier/mission').mkdir(parents=True)
    outside = tmp_path / 'secret.txt'
    outside.write_text('validation')
    with pytest.raises(PermissionError):
        _workspace(tmp_path)
    with pytest.raises(PermissionError):
        run_task(Mock(), 'execute tout', tmp_path)
    try:
        os.link(outside, tmp_path / 'atelier/mission/link.txt')
    except PermissionError:
        pytest.skip('Ce compte Windows ne peut pas creer de lien physique.')
    with pytest.raises(ValueError, match='physique'):
        _size(tmp_path / 'atelier/mission')
