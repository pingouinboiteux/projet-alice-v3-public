"""Exact local commands; document bodies are data, never instructions."""
import re
from protected_workspace import Workspace, check_local, checked_body

HELP = ('Espace protege :\n'
        'cree le document exemple.txt : ton texte\n'
        'modifie le document exemple.txt : nouveau texte\n'
        'lis le document exemple.txt\n'
        'historique du document exemple.txt\n'
        'restaure le document exemple.txt : identifiant de version\n'
        'exporte le document exemple.txt\n'
        'importe le document exemple.txt (copie UTF-8 deposee dans data/protected_workspace/imports)\n'
        'mes documents proteges ; journal des documents\n'
        'Les modifications et restaurations montrent le texte avant accord. '
        'Exports texte uniquement, jamais executes ; aucun acces aux dossiers personnels.')


def command(text):
    if not isinstance(text, str):
        return None
    if text.strip().casefold() in ('/documents', 'mes documents proteges', 'journal des documents'):
        return (text.strip().casefold(), None, None)
    match = re.fullmatch(r'(cree|crée|modifie|lis|exporte|importe|restaure) le document ([^\r\n:]+?)(?:\s*:\s?(.*))?',
                         text.strip(), re.I | re.S)
    if match:
        return match[1].lower().replace('é','e'), match[2].strip(), match[3]
    match = re.fullmatch(r'historique du document ([^\r\n:]+)', text.strip(), re.I)
    return ('historique', match[1].strip(), None) if match else None


def handle(text, source, confirm, cancelled=lambda:False, *, workspace=None):
    parsed = command(text)
    if parsed is None:
        return None
    check_local(source)
    store = workspace or Workspace()
    op, name, body = parsed
    def check():
        if cancelled():
            raise ValueError('protected_cancelled')
    try:
        check()
        if op == '/documents':
            return HELP
        if op == 'mes documents proteges':
            return 'Documents proteges :\n' + ('\n'.join(store.list(source=source)) or 'Aucun document.')
        if op == 'journal des documents':
            return 'Dernieres operations :\n' + ('\n'.join(
                f"{r['id']} : {r['action']} {r['name']} (version {r['revision']})"
                for r in store.journal(source=source)) or 'Aucune operation.')
        if op == 'historique':
            return 'Versions (plus recente en premier) :\n' + ('\n'.join(
                r['id']+' : '+r['reason'] for r in store.history(name, source=source)) or 'Aucune version.')
        if op == 'importe':
            check();revision=store.import_text(name,source=source)
            return 'Copie importee : '+name+' (version '+revision+'). Le fichier depose reste intact.'
        current = store.read(name, source=source)
        if op == 'lis':
            return current['body'] if current else 'Document introuvable.'
        if op == 'exporte':
            check()
            return 'Copie texte creee : ' + str(store.export(name, source=source))
        if op == 'cree':
            if body is None:
                return 'Ajoute le texte exact apres les deux-points.'
            checked_body(body)
            if current is not None:
                return 'Ce document existe deja. Demande une modification pour conserver son historique.'
            if source == 'voice' and not confirm('Creer '+name+' avec ce texte transcrit ?\n\n'+body):
                return 'Creation annulee.'
            check()
            revision = store.write(name, body, source=source, cancelled=cancelled)
            return 'Document cree et conserve : '+name+' (version '+revision+').'
        if not current:
            return 'Document introuvable.'
        if op == 'modifie':
            if body is None:
                return 'Ajoute le nouveau texte complet apres les deux-points.'
            checked_body(body)
            description = 'Modifier '+name+' ?\n\nAvant :\n'+current['body']+'\n\nApres :\n'+body
            if not confirm(description+'\n\nLa version precedente reste restaurable.'):
                return 'Modification annulee.'
            check()
            revision = store.write(name, body, source=source, expected=current['id'], cancelled=cancelled)
        elif op == 'restaure':
            if body is None or not re.fullmatch('[0-9a-f]{32}', body):
                return 'Indique un identifiant affiche dans historique du document '+name+'.'
            # Preview exactly the named version, not a model-generated summary.
            with store.database() as db:
                row = db.execute('SELECT body FROM revisions WHERE name=? AND id=?',
                                 (current['name'], body)).fetchone()
            if row is None:
                return 'Version introuvable pour ce document.'
            if not confirm('Restaurer '+name+' ?\n\nAvant :\n'+current['body']+
                           '\n\nApres :\n'+row['body']+'\n\nLa version actuelle reste conservee.'):
                return 'Restauration annulee.'
            check()
            revision = store.restore(name, body, source=source, expected=current['id'], cancelled=cancelled)
        else:
            return HELP
        return 'Document verifie : '+name+' (version '+revision+').'
    except (ValueError, OSError) as error:
        # No raw provider message or private paths in failures.
        reasons = {'protected_document_changed':'Le document a change entre-temps. Recommence pour relire la bonne version.',
                   'protected_text_filename_required':'Utilise un nom simple termine par .txt : lettres sans accent, chiffres, espaces, tirets ou underscores ; aucun chemin.',
                   'protected_cancelled':'Operation annulee.',
                   'protected_history_full':'Historique plein : aucune nouvelle modification autorisee.'}
        return reasons.get(str(error), 'Operation refusee : nom, emplacement, version ou taille non autorise. Aucun succes confirme.')
