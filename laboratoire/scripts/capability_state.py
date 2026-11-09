"""Small trusted runtime facts; never include external chat or personal memory."""
import json

def channel_state(channels):
    states={}
    for source in ('twitch','discord'):
        if channels is None or not channels.enabled.get(source):
            states[source]='off';continue
        process=channels.processes.get(source)
        if process is None or process.poll() is not None:
            states[source]='unavailable';continue
        status=getattr(channels,'connection_status',channels.last_status).get(source)
        states[source]=status if status in {'ready','connecting','disconnected'} else 'unknown'
    return states

def dialogue_context(channels):
    states=channel_state(channels)
    return ('\nMode protege : code libre et navigateur personnel desactives. '
        'Une mission de code locale avec /faire travaille dans un atelier MXC si son confinement est verifie. '
        'Son resultat reste a verifier avant toute utilisation hors atelier. '
        'Suivi : /missions, /mission identifiant, /reprendre identifiant. '
        'Un module Python ordinaire de laboratoire/scripts peut etre copie avec '
        '/faire fichier scripts/nom.py : demande ; /appliquer identifiant affiche '
        'la difference et demande un accord, /restaurer-code identifiant restaure '
        'la copie precedente apres accord. '
        'Documents texte versionnes via /documents ; copies importees uniquement dans le dossier reserve. '
        'Reponses publiques soumises a accord local pour chaque contenu. '
        'Historique des notes : /versions-note titre ; restauration : /restaurer-note titre | version. '
        'Pas de machine virtuelle installee ni de garantie de confinement Windows complet. '
        'Lecture d ecran locale disponible avec Alice-vision.bat : /ecran regarde 1, '
        '/ecran surveille 1 et /ecran stop. Le mode vision charge le projecteur du meme modele. '
        'Sans retour de cet observateur tu ne sais pas ce qui est affiche. '
        'Ses observations restent hors memoire et outils : remarques vocales breves en prive, '
        'ecrites en contexte public. Les morts repetees ne sont comptees que dans un jeu reconnu. '
        '\nEtat technique fourni par le programme pour ce tour, pas un souvenir : '
        +json.dumps(states,ensure_ascii=False)+'. off=coupe, ready=connexion etablie, '
        'connecting=en connexion, disconnected=deconnecte, unavailable=processus absent, '
        'unknown=etat non confirme. Le raccord Twitch lit le chat et peut repondre '
        'avec ta voix locale aux messages qui te nomment; il ne publie aucun texte '
        'sur Twitch. Discord sert au dialogue vocal du salon configure. Ces deux '
        'canaux n ont aucun droit d action sur le PC ni acces aux souvenirs prives de Proprietaire. Ils ont des echanges publics separes par auteur et plateforme. '
        'Une connexion ready ne prouve pas qu un message particulier a ete recu. '
        'Les boutons de la fenetre connectent les canaux; ouvrir leur site dans le '
        'navigateur ne connecte pas le chat. Une demande locale peut creer une note '
        'avec titre et texte explicites ; une demande claire peut etre executee sans bouton '
        'apres controle. Les notes sont separees des souvenirs et conservees apres fermeture. '
        'Tu peux aussi lister les notes, lire une note nommee ou remplacer son texte '
        'complet apres verification de l ancienne et de la nouvelle version. '
        'Pas de suppression ni renommage. Une creation n ecrase pas un titre existant. '
        'Une note demandee ou preparee n est pas '
        'encore enregistree ; seul le retour du controleur le confirme. '
        'Pour le Bloc-notes Windows, une demande locale explicite peut saisir un texte '
        'exact dans un document vide, avec activation de la fenetre et relecture. '
        'Il faut une fenetre unique ou son titre exact ; un texte deja identique '
        'ne sera pas ajoute une seconde fois. Les autres contenus existants ne sont '
        'pas modifies. Cette action est refusee pendant un jeu ; aucun enregistrement '
        'de fichier ni pilotage general du PC n est disponible par ce chemin. '
        'Seul le resultat verifie du controleur confirme la saisie. '
        'Pour le Web public, une demande locale peut fournir une URL HTTPS, le nom '
        'exact d un lien et une question sur la page d arrivee. Le controleur suit '
        'au plus un lien de meme origine dans un profil isole, puis verifie un extrait. '
        'Tu ne vois pas le navigateur personnel ni les comptes connectes. Un lien '
        'manquant, ambigu ou modifie impose une precision ; aucune lecture ne doit '
        'etre annoncee avant le retour verifie. Le contenu Web reste hors souvenirs. '
        'Tu peux aussi chercher une information precise depuis une page HTTPS fournie, '
        'en consultant un nombre limite de pages liees de meme origine. La reponse '
        'doit etre appuyee par un extrait verifie ; une limite ou une ambiguite est signalee. '
        'Une demande locale peut aussi chercher une information sur le Web public sans URL, avec sources verifiees et limites signalees. Aucun acces aux comptes. '
        'Tu es l interlocutrice de cette fenetre.')
