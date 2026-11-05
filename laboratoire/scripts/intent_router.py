"""Language understanding proposes finite actions; it never executes commands."""
import json
import re
from action_policy import Action, validate_url, SITES, normalize

ROUTING = '''Pour cette reponse, retourne uniquement un objet JSON avec exactement
les champs demandes en classant UNIQUEMENT le dernier message utilisateur.
L'historique donne le contexte, pas une liste d'ordres restant a executer.
Un tour turn_state=closed est termine, qu'il ait abouti, ete annule ou echoue.
Un remerciement ou constat de resultat ne demande pas de refaire une action.
Une nouvelle execution exige une nouvelle demande dans le message actuel;
une demande explicite comme "recommence" peut utiliser le contexte precedent.
Retourne uniquement
les champs kind, value, reply. kind est chat, status, volume, volume_delta, mute,
open, search, web_read, wiki_search, code ou memory_forget. Pour chat, value=null et reply contient ta reponse naturelle.
Pour status, value=null. volume accepte un entier de 0 a 100, volume_delta
seulement -10 pour baisser ou 10 pour monter. mute=true coupe le son, mute=false le reactive.
Le reglage sonore est global Windows, pas propre a une application.
Un niveau chiffre, y compris zero, demande volume, pas mute.
open accepte une URL HTTPS precise demandee par
l'utilisateur, search les termes explicitement demandes pour Google.
Un site nomme explicitement peut etre ouvert : YouTube=https://www.youtube.com/,
Google=https://www.google.com/, Wikipedia=https://fr.wikipedia.org/,
Twitch=https://www.twitch.tv/. Utilise ces URL pour kind=open.
web_read lit une adresse HTTPS explicitement fournie par l'utilisateur.
Si l'utilisateur demande de lire, expliquer ou resumer une page avec son URL,
choisis obligatoirement web_read. Ne fournis jamais un resume de memoire dans
chat : aucune page n'a encore ete lue. Les outils doivent fournir les preuves.
wiki_search cherche une notion sur Wikipedia (value=termes, 300 caracteres maximum).
Ce n'est pas une recherche generale du Web : pour Google ou une actualite,
choisir search pour ouvrir les resultats dans le navigateur.
code prepare une creation/modification de fichiers ou de code dans l'atelier
isole, apres confirmation. value contient la demande. Une demande naturelle
comme creer une petite page ou un fichier peut choisir code sans mot special.
Ne choisis jamais code pour modifier Windows, les permissions, des fichiers
personnels hors atelier, installer un programme ou faire une operation interdite.
Pour une action, reply explique brievement la proposition sans dire qu'elle
est deja executee. Une negation, une citation, une hypothese ou une question
sur une commande n'est pas un ordre d'execution : choisir chat.
Si la demande est ambigue, choisir chat et demander une precision.
Ne transforme pas une demande de conseil sur un jeu en modification de volume.
Tu ne peux proposer aucune autre action ni une commande de terminal.
Exemples de decisions (reply est une proposition, pas un resultat) :
"Resume https://example.org/article" -> kind=web_read, value=https://example.org/article.
"Ouvre le site YouTube s il te plait" -> kind=open, value=https://www.youtube.com/.
"Peux-tu creer un fichier bonjour.txt ?" -> kind=code, value=la demande.
"Ne cree pas de fichier" -> kind=chat, value=null.
status mesure seulement les ressources ou programmes actuels du PC, sur demande de mesure.
Une explication generale sur leur fonctionnement, ou une question sur la vie de la personne, reste chat.
Pour une demande directe d'effacer ou d'oublier un souvenir personnel, choisir
memory_forget avec value=demande originale. Ce choix prepare un apercu et une
confirmation, jamais une suppression automatique. Une citation ou negation reste chat.
'''

SCHEMA = {'type': 'object', 'properties': {
    'kind': {'type': 'string', 'enum': ['chat', 'status', 'volume', 'volume_delta', 'mute', 'open', 'search', 'web_read', 'wiki_search', 'code', 'memory_forget']},
    'value': {'anyOf': [{'type': 'null'}, {'type': 'integer'}, {'type': 'boolean'}, {'type': 'string'}]},
    'reply': {'type': 'string'}}, 'required': ['kind', 'value', 'reply'], 'additionalProperties': False}


def decode(text):
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'kind', 'value', 'reply'}:
        raise ValueError('Proposition non conforme')
    kind, argument, reply = value['kind'], value['value'], value['reply']
    if not isinstance(reply, str) or len(reply) > 2000:
        raise ValueError('Reponse invalide')
    if kind in {'chat', 'status'}:
        valid = argument is None and (bool(reply.strip()) or kind == 'status')
    elif kind == 'volume':
        valid = type(argument) is int and 0 <= argument <= 100
    elif kind == 'volume_delta':
        valid = type(argument) is int and argument in (-10, 10)
    elif kind == 'mute':
        valid = type(argument) is bool
    elif kind in {'open', 'web_read'}:
        if kind == 'open' and isinstance(argument, str):
            argument = SITES.get(normalize(argument), argument)
        valid = isinstance(argument, str) and bool(validate_url(argument))
    elif kind == 'search':
        valid = isinstance(argument, str) and 0 < len(argument) <= 500
        if valid:
            from urllib.parse import quote_plus
            argument = 'https://www.google.com/search?q=' + quote_plus(argument)
    elif kind in {'wiki_search', 'code', 'memory_forget'}:
        valid = isinstance(argument, str) and 0 < len(argument) <= (300 if kind == 'wiki_search' else 5000)
    else:
        valid = False
    if not valid:
        raise ValueError('Action hors permissions')
    return Action(kind, argument), reply


def route(session, messages, text):
    trial = [{'role': 'system', 'content': messages[0]['content'] + '\n' + ROUTING}]
    trial += messages[1:][-12:] + [{'role': 'user', 'content': text}]
    raw, _, _ = session.ask(trial, response_schema=SCHEMA)
    try:
        action, reply = decode(raw)
        if action.kind == 'volume':
            from volume_grounding import supports_volume
            if not supports_volume(text, action.value):
                return Action('clarify'), ('Je ne trouve pas le niveau propose dans ta demande. '
                    'Veux-tu retirer la sourdine ou choisir un pourcentage de volume ?')
        if action.kind == 'web_read':
            supplied = [url.rstrip('.,;!?)]}') for url in re.findall(r'https://[^\s<>"\x27]+', text)]
            if action.value not in supplied:
                raise ValueError('Adresse de lecture non fournie par utilisateur')
        if action.kind in {'code','memory_forget'}:
            action = Action(action.kind, text)  # Keep the user's request, not a model rewrite.
        return action, reply
    except (ValueError, TypeError):
        return Action('clarify'), 'Je n ai pas obtenu une demande suffisamment claire. Peux-tu reformuler ? Aucune action n a ete executee.'


def describe(action):
    return {'volume': f'Fixer le volume a {action.value} %',
            'volume_delta': f'Modifier le volume de {action.value} points',
            'mute': 'Couper le son' if action.value else 'Reactiver le son',
            'open': f'Ouvrir {action.value}', 'search': f'Rechercher via {action.value}',
            'status': 'Lire les ressources du PC'}.get(action.kind, 'Action inconnue')
