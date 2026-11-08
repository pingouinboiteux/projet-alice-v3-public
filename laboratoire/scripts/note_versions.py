"""Version copies before persistent note replacement; explicit local recovery."""
import hashlib
from protected_workspace import Workspace, check_local
from observer_note_pending import PendingNoteReview


def version_store(storage):
    return Workspace() if storage.is_personal else Workspace(storage.directory.parent/'protected_history')


def document_name(title):
    return 'note_'+hashlib.sha256(title.encode('utf-8')).hexdigest()[:32]+'.txt'


def remember(storage, note):
    if storage is None:
        return  # Disposable test wiki, no persistence to protect.
    storage._validate_path()
    store=version_store(storage); name=document_name(note['title'])
    current=store.read(name,source='text')
    return store.write(name,note['body'],source='text',expected=current['id'] if current else None)


def handle(text, source, session, factory, executor, confirm, cancelled):
    if not text.startswith(('/versions-note ', '/restaurer-note ')):
        return None
    check_local(source)
    restoring=text.startswith('/restaurer-note ')
    value=text.split(' ',1)[1].strip()
    if restoring:
        if ' | ' not in value:
            return {'status':'clarify','reply':'Utilise /restaurer-note titre exact | identifiant de version.'}
        title,revision=value.rsplit(' | ',1)
    else:
        title=value
    backend=None; pending=PendingNoteReview()
    def check():
        session.check()
        if cancelled():raise ValueError('note_restore_cancelled')
    try:
        check(); backend=factory(check)
        if backend.storage is None:
            raise ValueError('persistent_note_required')
        store=version_store(backend.storage); name=document_name(title)
        if not restoring:
            rows=store.history(name,source=source)
            return {'status':'listed','reply':'Versions de '+title+' :\n'+(
                '\n'.join(r['id'] for r in rows) or 'Aucune version conservee pour cette note.')}
        with store.database() as db:
            row=db.execute('SELECT body,hash FROM revisions WHERE name=? AND id=?',(name,revision)).fetchone()
        from protected_workspace import digest
        if row is None or digest(row['body'])!=row['hash']:
            raise ValueError('note_restore_version_invalid')
        target={'title':title,'body':row['body']}
        backend.start();existing=backend.read_note(title);check()
        if existing is None:raise ValueError('note_restore_missing')
        if existing==target:return {'status':'unchanged','reply':'La note contient deja cette version.'}
        pending.propose(target,'local_text' if source=='text' else 'voice')
        review=pending.review()
        if not confirm('Restaurer la note '+title+' ?\n\nAvant :\n'+existing['body']+
                       '\n\nApres :\n'+target['body']+'\n\nLa version actuelle sera conservee.'):
            return {'status':'cancelled','reply':'Restauration annulee.'}
        check();authorization=pending.confirm(review['ticket'],'oui')
        backend.prepare_edit(existing)
        def commit():
            check();return pending.claim(authorization)
        outcome=executor(session,backend,target,commit);check()
        if outcome.get('passed') and backend.verify_persisted(target):
            return {'status':'restored','reply':'Note restauree et relue : '+title+'.'}
        return {'status':'unverified','reply':'Restauration non confirmee ; aucune nouvelle tentative automatique.'}
    except Exception as error:
        return {'status':'failed','error_type':type(error).__name__,
                'reply':'Restauration ou historique indisponible. Aucun succes confirme.'}
    finally:
        pending.cancel()
        if backend is not None:backend.close()
