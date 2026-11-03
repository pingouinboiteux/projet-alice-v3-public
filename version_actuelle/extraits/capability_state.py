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
    return ('\nEtat technique fourni par le programme pour ce tour, pas un souvenir : '
        +json.dumps(states,ensure_ascii=False)+'. off=coupe, ready=connexion etablie, '
        'connecting=en connexion, disconnected=deconnecte, unavailable=processus absent, '
        'unknown=etat non confirme. Le raccord Twitch lit le chat et peut repondre '
        'avec ta voix locale aux messages qui te nomment; il ne publie aucun texte '
        'sur Twitch. Discord sert au dialogue vocal du salon configure. Ces deux '
        'canaux n ont aucun droit d action sur le PC ni acces aux souvenirs prives du proprietaire. Ils ont des echanges publics separes par auteur et plateforme. '
        'Une connexion ready ne prouve pas qu un message particulier a ete recu. '
        'Les boutons de la fenetre connectent les canaux; ouvrir leur site dans le '
        'navigateur ne connecte pas le chat. Tu es l interlocutrice de cette fenetre.')
