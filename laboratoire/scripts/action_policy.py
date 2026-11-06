"""Explicit finite capabilities. Model text never becomes a Windows command."""
from dataclasses import dataclass
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit, quote_plus, unquote

SITES = {'google': 'https://www.google.com/', 'youtube': 'https://www.youtube.com/',
         'wikipedia': 'https://fr.wikipedia.org/', 'twitch': 'https://www.twitch.tv/'}


def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold())
                   if not unicodedata.combining(c)).replace('’', "'").strip(' .!?')


def validate_url(url):
    if len(url) > 2000 or any(c.isspace() or ord(c) < 32 for c in url) or '\\' in url:
        raise ValueError('Adresse invalide')
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower().rstrip('.')
    if parsed.scheme != 'https' or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError('Seules les adresses HTTPS publiques sans identifiants sont autorisees')
    if not host or '.' not in host or host.endswith(('.local', '.localhost', '.internal', '.lan')):
        raise ValueError('Adresse locale refusee')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ValueError('Adresse IP directe refusee')
    # Check the requested file, not the hostname: .com is also a public TLD.
    if re.search(r'\.(exe|msi|bat|cmd|ps1|scr|com|zip|7z|rar|iso)$', unquote(parsed.path).rstrip('/'), re.I):
        raise ValueError('Telechargement executable ou archive non autorise par cet outil')
    return url


@dataclass(frozen=True)
class Action:
    kind: str
    value: object = None


def parse(text):
    rendered=re.fullmatch(r'/voir\s+(https://\S+)(?:\s+.*)?',text.strip(),re.I|re.S)
    if rendered:return Action('web_observe',validate_url(rendered[1]))
    clean = normalize(text)
    if clean in {'arrete alice', 'quitte', 'quitter', 'stop alice', '/quitter'}:
        return Action('quit')
    if clean in {'/nouveau', 'nouvelle conversation', 'efface cette conversation'}:
        return Action('reset')
    if clean in {'pause', 'coupe le micro', 'arrete de m ecouter', "arrete de m'ecouter"}:
        return Action('pause')
    if clean in {'annule', 'annule le dernier reglage', '/annuler'}:
        return Action('undo')
    if clean in {'etat du pc', "quel est l'etat du pc", 'ressources', '/etat'}:
        return Action('status')
    if clean in {'baisse le son', 'baisse le volume'}:
        return Action('volume_delta', -10)
    if clean in {'monte le son', 'augmente le volume', 'monte le volume'}:
        return Action('volume_delta', 10)
    if clean in {'coupe le son', 'mets le son en sourdine'}:
        return Action('mute', True)
    if clean in {'remets le son', 'reactive le son'}:
        return Action('mute', False)
    match = re.fullmatch(r'(?:mets|regle) (?:le son|le volume) a (\d{1,3})(?:\s*%| pour cent)?', clean)
    if match:
        value = int(match[1])
        if value > 100:
            raise ValueError('Le volume doit etre compris entre 0 et 100')
        return Action('volume', value)
    match = re.fullmatch(r'(?:ouvre|va sur) (.+)', clean)
    if match:
        name = match[1]
        if name in SITES:
            return Action('open', SITES[name])
        original = re.sub(r'^(?:ouvre|va sur)\s+', '', text.strip(), flags=re.I)
        if original.startswith('https://'):
            return Action('open', validate_url(original.rstrip('.,;!?)]}')))
        return Action('chat', text)
    match = re.match(r'^cherche sur google\s+(.+)$', text.strip(), re.I)
    if match:
        return Action('search', 'https://www.google.com/search?q=' + quote_plus(match[1][:500]))
    match = re.match(r'^(?:/faire\s+|dans l[’\x27]atelier[,]?\s+)(.+)$', text.strip(), re.I)
    if match:
        return Action('code', match[1])
    return Action('chat', text)


class Actions:
    def __init__(self, pc, browser, confirm, monitor):
        self.pc, self.browser, self.confirm, self.monitor = pc, browser, confirm, monitor
        self.previous = None

    def execute(self, action, *, automatic_open=False, cancelled=lambda:False):
        if action.kind in {'volume', 'volume_delta', 'mute'}:
            old = self.pc.read_volume()
            if action.kind == 'mute':
                result = self.pc.set_mute(action.value)
            else:
                target = action.value if action.kind == 'volume' else max(0, min(100, old['percent'] + action.value))
                if target > 70 and target > old['percent'] and not self.confirm(f'Monter le volume a {target} % ?'):
                    return 'Modification annulee.'
                result = self.pc.set_volume(target)
            self.previous = old
            return f"Volume verifie a {result['percent']} pour cent. " + ('Le son est coupe.' if result['muted'] else '')
        if action.kind == 'undo':
            if self.previous is None:
                return 'Aucun reglage de son a annuler dans cette session.'
            old = self.previous
            self.pc.set_volume(old['percent'])
            self.pc.set_mute(old['muted'])
            self.previous = None
            return 'Le precedent reglage du son a ete retabli et verifie.'
        if action.kind in {'open', 'search'}:
            url = validate_url(action.value)
            if action.kind=='open' and automatic_open is True:
                from web_reader import public_addresses
                public_addresses(urlsplit(url).hostname)
                if cancelled():return 'Ouverture annulee.'
            elif not self.confirm('Ouvrir cette adresse dans ton navigateur ?\n' + url):
                return 'Ouverture annulee.'
            if not self.browser(url):
                raise RuntimeError('Le navigateur ne confirme pas la prise en charge')
            return 'La demande d ouverture a ete transmise au navigateur. Je ne lis pas automatiquement cette page.'
        if action.kind == 'status':
            data = self.monitor.sample()
            cpu = 'en cours de mesure' if data['cpu_percent'] is None else str(round(data['cpu_percent'])) + ' pour cent'
            return f"Il reste {data['ram_free_gib']} gigaoctets de RAM. Charge du processeur : {cpu}. {len(data['programs'])} noms de programmes reperes."
        if action.kind == 'unsupported':
            return action.value
        raise ValueError('Action non geree')
