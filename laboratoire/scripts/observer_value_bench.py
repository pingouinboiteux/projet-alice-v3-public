"""Exact values, precommit fault injection and bounded real app qualification."""
import argparse
import json
import time
from observer_action_bench import ObserverSession, payload_for
from observer_value_contract import ValueContract
from observer_checked_actions import CheckedActions
from vision_bench_runtime import save, strict_json
from model_profile import template_settings
from chat import ROOT

REPORTS = ROOT / 'data/validation/validation_values_20261105'

def saved_exact(snapshot, target, contract):
    saved = snapshot.get('saved')
    return type(saved) is dict and set(saved) == set(target) and contract.check_values(saved)['ok']

def complete(session, backend, target, before_commit=None):
    contract = ValueContract.from_user_values(target)
    checked = CheckedActions(backend, contract, before_commit=before_commit)
    rows = []
    for turn in range(9):
        session.check()
        before = checked.observe()
        if saved_exact(before, target, contract):
            return {'passed': True, 'steps': rows, 'final': before}
        history = [{'action': r['action'], 'resultat': r['result']['reason']} for r in rows]
        payload = payload_for('Enregistre exactement les valeurs utilisateur indiquees. Chaque valeur est litterale.', before, history)
        payload['messages'][0]['content'] += (
            ' Les valeurs utilisateur ont des references fiables. Utilise de preference '
            '{"op":"fill","target":"champ","value_ref":"user:champ"}, '
            'ou select/check avec value_ref, pour inserer la valeur exacte sans la reecrire. '
            'Apres un refus, lis le resultat et choisis une action corrigee. '
            'Les references ne changent pas selon le texte de la page.')
        user = json.loads(payload['messages'][1]['content'])
        user['valeurs_utilisateur'] = contract.references()
        payload['messages'][1]['content'] = json.dumps(user, ensure_ascii=False)
        payload['chat_template_kwargs'] = template_settings(session.model_spec)
        start = time.perf_counter()
        response = session.request('/v1/chat/completions', payload, timeout=60)
        choice = response['choices'][0]
        if choice['finish_reason'] != 'stop':
            return {'passed': False, 'reason': 'truncated', 'steps': rows}
        action = strict_json(choice['message']['content'])
        row = {'action': action, 'model_ms': (time.perf_counter()-start)*1000, 'before': before}
        if action == {'op': 'done'}:
            return {'passed': False, 'reason': 'premature_done', 'steps': rows, 'last_action': action}
        row['result'] = checked.act(action, before)
        row['after'] = checked.observe()
        rows.append(row)
        if row['result']['ok'] and row['result']['verified'] and saved_exact(row['after'], target, contract):
            return {'passed': True, 'steps': rows, 'final': row['after']}
    return {'passed': False, 'reason': 'budget', 'steps': rows}

def probes(backend, target):
    contract = ValueContract.from_user_values(target)
    checked = CheckedActions(backend, contract)
    before = checked.observe()
    if any(e['id'] == 'nav_form' for e in before['elements']):
        backend.act({'op': 'click', 'target': 'nav_form'}, before)
    for field, value in target.items():
        op = 'check' if type(value) is bool else 'select' if field == 'category' else 'fill'
        result = checked.act({'op': op, 'target': field, 'value_ref': 'user:'+field}, checked.observe())
        if not result['ok']: raise RuntimeError('Probe setup failed: '+str(result))
    prior = backend._read()
    result = checked.act({'op': 'fill', 'target': 'title', 'value': 'altered'}, checked.observe())
    literal = result['reason'] == 'literal_value_mismatch' and backend._read() == prior
    # Simulate an application-side mutation, bypassing the model as a controlled fault.
    backend.guard()
    if hasattr(backend, 'tamper_field_for_test'):
        backend.tamper_field_for_test('title', 'altered')
    else:
        backend.page.locator('#title').fill('altered')
    snapshot = checked.observe()
    prior = backend._read()
    rejected = checked.act({'op': 'click', 'target': 'save'}, snapshot)
    unchanged = backend._read() == prior and prior.get('saved') is None
    return {'literal_refused_without_dispatch': literal and not result['dispatched'],
            'wrong_values_prevent_commit': rejected['reason'] == 'precommit_values_mismatch'
                 and not rejected['dispatched'] and unchanged, 'rejection': rejected}

def run(app=False):
    from observer_browser import BrowserDemo
    if app:
        from observer_tiddlywiki import TiddlyWikiApp
    report = {'status': 'starting', 'app': 'TiddlyWiki5.4.1' if app else 'demo',
              'cases': [], 'cleanup': [], 'contract_source': 'explicit synthetic user field values; no free-form intent extraction'}
    path = REPORTS / (('app_' if app else 'demo_')+time.strftime('%H%M%S')+'.json')
    session = ObserverSession()
    backend = None
    try:
        session.start()
        report['device'] = session.device
        report['games_present'] = session.games_present
        cases = ([{'title': 'validation_note_angles', 'body': 'Verifier <b>le texte</b> & conserver 09:15.'},
                  {'title': 'validation_note_accents', 'body': 'Été — coût : 15,60 EUR\nDeuxième ligne.'},
                  {'title': 'validation_note_espaces', 'body': 'Garder  deux espaces et "les guillemets".'}]
                 if app else [
                    {'title': 'Verifier <b>le texte</b>', 'category': 'travail', 'reminder': False},
                    {'title': 'Été — 15,60 EUR', 'category': 'loisir', 'reminder': True},
                    {'title': 'Garder  deux espaces', 'category': 'personnel', 'reminder': False}])
        for index, target in enumerate(cases):
            backend = TiddlyWikiApp(guard=session.check) if app else BrowserDemo(guard=session.check)
            session.browser_demo = backend
            try:
                backend.start()
                if app: backend.prepare_new()
                if index == 0:
                    report['probes'] = probes(backend, target)
                    if not all(report['probes'][k] for k in ('literal_refused_without_dispatch', 'wrong_values_prevent_commit')):
                        raise RuntimeError('Precommit probe failed')
                outcome = complete(session, backend, target)
                if app and outcome['passed']:
                    outcome['persisted'] = backend.verify_persisted(target)
                    outcome['persistence_evidence'] = backend.persistence_evidence
                    outcome['passed'] = outcome['persisted'] is True
                report['cases'].append({'target': target, **outcome})
                save(path, report)
                print(json.dumps({'case': index, 'passed': outcome['passed']}), flush=True)
            finally:
                if hasattr(backend, 'diagnostics'):
                    report.setdefault('app_diagnostics', []).append(backend.diagnostics)
                backend.close()
                report['cleanup'].append(backend.owned_stopped)
                session.browser_demo = None
                backend = None
        report['status'] = 'complete'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if backend:
            try: backend.close()
            except Exception as error: report['browser_cleanup_error'] = repr(error)
        try: session.close()
        except Exception as error: report.update(status='cleanup_failed', cleanup_error=repr(error))
        report['model_stopped'] = all(p.poll() is not None for p in session.children.values())
        report['minimum_free_ram'] = session.minimum_ram
        if session.frame_guard:
            report['fps_guard_report'] = str(session.frame_guard.report_path.relative_to(ROOT))
        save(path, report)
        print('REPORT', path.relative_to(ROOT), report['status'], flush=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--app', action='store_true')
    run(parser.parse_args().app)
